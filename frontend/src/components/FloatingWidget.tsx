import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow, LogicalPosition, LogicalSize } from "@tauri-apps/api/window";
import type { Lang } from "../i18n/lang";
import "./FloatingWidget.css";

type Edge = "left" | "right";

const EDGE_KEY = "floating-edge";
const POS_KEY = "floating-pos";
const DRAG_THRESHOLD = 4;
const DRAG_DELAY = 200;
const BALL_SIZE = 56;
const MENU_W = 258;
const MENU_H = 300;

const copy = {
  zh: {
    capture: "截图OCR",
    pasteOcr: "粘贴OCR",
    clipboard: "剪切板",
    memo: "备忘录",
    keys: "密钥",
    settings: "设置",
    hide: "退出悬浮窗",
    menu: "悬浮窗菜单",
  },
  en: {
    capture: "Screenshot OCR",
    pasteOcr: "Paste OCR",
    clipboard: "Clipboard",
    memo: "Memo",
    keys: "Keys",
    settings: "Settings",
    hide: "Hide Widget",
    menu: "Floating widget menu",
  },
} as const;

const readStored = (key: string) => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeStored = (key: string, value: string) => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage can be unavailable; the widget still works without persistence */
  }
};

interface DragState {
  timer: number;
  startX: number;
  startY: number;
}

export function FloatingWidget({ language = "zh" }: { language?: Lang }) {
  const t = copy[language];
  const [edge, setEdge] = useState<Edge>(() => (readStored(EDGE_KEY) === "left" ? "left" : "right"));
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const drag = useRef<DragState | null>(null);

  useLayoutEffect(() => {
    document.body.classList.add("floating-body");
    return () => document.body.classList.remove("floating-body");
  }, []);

  useEffect(() => {
    const raw = readStored(POS_KEY);
    if (!raw) return;
    try {
      const position = JSON.parse(raw) as { x?: number; y?: number };
      if (typeof position.x === "number" && typeof position.y === "number") {
        void getCurrentWindow().setPosition(new LogicalPosition(Math.round(position.x), Math.round(position.y)));
      }
    } catch {
      /* ignore malformed position */
    }
  }, []);

  const showMain = async () => {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const main = await WebviewWindow.getByLabel("main");
    if (!main) return;
    await main.show();
    await main.setFocus();
    return main;
  };

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await action();
    } catch {
      /* the widget must never surface a blocking error dialog */
    } finally {
      setBusy(false);
    }
  };

  const request = (intent: string) =>
    void run(async () => {
      setOpen(false);
      const main = await showMain();
      await main?.emit("floating-intent", intent);
    });

  const hideWidget = () => void run(async () => { await invoke("set_floating_widget_visible", { visible: false }); });

  const actions: { id: string; label: string; onClick: () => void; icon: string }[] = [
    { id: "capture", label: t.capture, onClick: () => request("capture"), icon: "/assets/icons/capture.svg" },
    { id: "paste_ocr", label: t.pasteOcr, onClick: () => request("paste_ocr"), icon: "/assets/icons/text-ocr.svg" },
    { id: "clipboard", label: t.clipboard, onClick: () => request("clipboard"), icon: "/assets/icons/clipboard.svg" },
    { id: "memo", label: t.memo, onClick: () => request("memo"), icon: "/assets/icons/memo.svg" },
    { id: "keys", label: t.keys, onClick: () => request("keys"), icon: "/assets/icons/key.svg" },
    { id: "settings", label: t.settings, onClick: () => request("settings"), icon: "/assets/icons/settings.svg" },
  ];

  const resizeForMenu = async (menuOpen: boolean, currentEdge: Edge) => {
    const w = getCurrentWindow();
    const size = await w.outerSize();
    const scale = await w.scaleFactor();
    const winW = size.width / scale;
    if (menuOpen) {
      if (winW === MENU_W) return;
      const nx = currentEdge === "right" ? (await w.outerPosition()).x / scale - (MENU_W - BALL_SIZE) : (await w.outerPosition()).x / scale;
      await w.setSize(new LogicalSize(MENU_W, MENU_H));
      await w.setPosition(new LogicalPosition(Math.round(nx), Math.round((await w.outerPosition()).y / scale)));
    } else {
      if (winW === BALL_SIZE) return;
      const nx = currentEdge === "right" ? (await w.outerPosition()).x / scale + (MENU_W - BALL_SIZE) : (await w.outerPosition()).x / scale;
      await w.setSize(new LogicalSize(BALL_SIZE, BALL_SIZE));
      await w.setPosition(new LogicalPosition(Math.round(nx), Math.round((await w.outerPosition()).y / scale)));
    }
  };

  const persistAfterDrag = async () => {
    const w = getCurrentWindow();
    const position = await w.outerPosition();
    const size = await w.outerSize();
    const scale = await w.scaleFactor();
    const winW = size.width / scale;
    const winH = size.height / scale;
    const screen = window.screen;
    let x = position.x / scale;
    let y = position.y / scale;
    x = Math.max(0, Math.min(x, screen.availWidth - winW));
    y = Math.max(0, Math.min(y, screen.availHeight - winH));
    if (x !== position.x / scale || y !== position.y / scale) {
      await w.setPosition(new LogicalPosition(Math.round(x), Math.round(y)));
    }
    const nextEdge: Edge = x <= (screen.availWidth - winW) / 2 ? "left" : "right";
    writeStored(POS_KEY, JSON.stringify({ x, y }));
    writeStored(EDGE_KEY, nextEdge);
    setEdge(nextEdge);
    setOpen(false);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    drag.current = {
      timer: window.setTimeout(() => {
        drag.current = null;
        const w = getCurrentWindow();
        void w.startDragging().then(() => void persistAfterDrag());
      }, DRAG_DELAY),
      startX: event.screenX,
      startY: event.screenY,
    };
  };

  const onPointerUp = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    if (!state) return;
    drag.current = null;
    window.clearTimeout(state.timer);
    const moved =
      Math.abs(event.screenX - state.startX) > DRAG_THRESHOLD ||
      Math.abs(event.screenY - state.startY) > DRAG_THRESHOLD;
    if (moved) {
      void persistAfterDrag();
    } else {
      setOpen((current) => {
        const next = !current;
        void resizeForMenu(next, edge);
        return next;
      });
    }
  };

  return (
    <section className={`floating-widget is-${edge}${open ? " is-open" : ""}`} aria-label={t.menu}>
      <div className="floating-anchor">
        {open && (
          <nav className="floating-menu" aria-label={t.menu}>
            {actions.map((action) => (
              <button
                key={action.id}
                type="button"
                disabled={busy}
                onClick={action.onClick}
                title={action.label}
              >
                <img src={action.icon} alt="" aria-hidden="true" />
                <span className="floating-action-label">{action.label}</span>
              </button>
            ))}
            <button type="button" className="floating-hide" disabled={busy} onClick={hideWidget} title={t.hide}>
              <img src="/assets/icons/exit.svg" alt="" aria-hidden="true" />
              <span className="floating-action-label">{t.hide}</span>
            </button>
          </nav>
        )}
        <button
          type="button"
          className="floating-ball"
          aria-label={t.menu}
          aria-expanded={open}
          title={t.menu}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setOpen((current) => !current);
            }
          }}
        >
          <img src="/assets/icons/menu.svg" alt="" aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

export default FloatingWidget;