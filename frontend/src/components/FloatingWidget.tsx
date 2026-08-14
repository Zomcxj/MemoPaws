import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow, LogicalPosition } from "@tauri-apps/api/window";
import type { Lang } from "../i18n/lang";
import "./FloatingWidget.css";

type Edge = "left" | "right";

const EDGE_KEY = "floating-edge";
const POS_KEY = "floating-pos";
const DRAG_THRESHOLD = 4;

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
  winX: number;
  winY: number;
  cursorX: number;
  cursorY: number;
  moved: boolean;
}

export function FloatingWidget({ language = "zh" }: { language?: Lang }) {
  const t = copy[language];
  const [edge, setEdge] = useState<Edge>(() => (readStored(EDGE_KEY) === "left" ? "left" : "right"));
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const drag = useRef<DragState | null>(null);

  useEffect(() => {
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

  const snapToEdge = async () => {
    // Snap against the primary display bounds, mirroring the Python edition.
    const screen = window.screen;
    const mx = 0;
    const my = 0;
    const mw = screen.availWidth;
    const mh = screen.availHeight;
    const w = getCurrentWindow();
    const position = await w.outerPosition();
    const size = await w.outerSize();
    const scale = await w.scaleFactor();
    const winW = size.width / scale;
    const winH = size.height / scale;
    const winX = position.x / scale;
    const winY = position.y / scale;
    const leftDist = winX - mx;
    const rightDist = mx + mw - (winX + winW);
    const nextEdge: Edge = leftDist <= rightDist ? "left" : "right";
    const x = nextEdge === "left" ? mx : mx + mw - winW;
    const y = Math.max(my, Math.min(winY, my + mh - winH));
    writeStored(POS_KEY, JSON.stringify({ x, y }));
    writeStored(EDGE_KEY, nextEdge);
    setEdge(nextEdge);
    setOpen(false);
    void w.setPosition(new LogicalPosition(Math.round(x), Math.round(y)));
  };

  const onPointerDown = async (event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const w = getCurrentWindow();
    const position = await w.outerPosition();
    const scale = await w.scaleFactor();
    drag.current = { winX: position.x / scale, winY: position.y / scale, cursorX: event.screenX, cursorY: event.screenY, moved: false };
    setOpen(false);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    if (!state) return;
    const dx = event.screenX - state.cursorX;
    const dy = event.screenY - state.cursorY;
    if (!state.moved && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
    state.moved = true;
    void getCurrentWindow().setPosition(new LogicalPosition(Math.round(state.winX + dx), Math.round(state.winY + dy)));
  };

  const onPointerUp = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    drag.current = null;
    if (!state) return;
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* already released */ }
    if (state.moved) {
      void snapToEdge();
    } else {
      setOpen((current) => !current);
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
          onPointerDown={(event) => void onPointerDown(event)}
          onPointerMove={onPointerMove}
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