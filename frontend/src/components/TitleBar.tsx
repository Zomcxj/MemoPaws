import { useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./TitleBar.css";

type WindowApi = ReturnType<typeof getCurrentWindow>;

function getWindow(): WindowApi | null {
  try {
    return getCurrentWindow();
  } catch {
    return null;
  }
}

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false);
  const windowRef = useRef<WindowApi | null>(null);

  useEffect(() => {
    const appWindow = getWindow();
    windowRef.current = appWindow;
    if (!appWindow) return;
    void appWindow.isMaximized().then(setMaximized).catch(() => {});
  }, []);

  const minimize = () => void windowRef.current?.minimize().catch(() => {});
  const toggleMaximize = () => {
    const appWindow = windowRef.current;
    if (!appWindow) return;
    void appWindow.toggleMaximize()
      .then(() => appWindow.isMaximized())
      .then(setMaximized)
      .catch(() => {});
  };
  const close = () => void windowRef.current?.close().catch(() => {});
  const startDragging = () => void windowRef.current?.startDragging().catch(() => {});

  return (
    <header
      className="title-bar"
      data-tauri-drag-region
      onMouseDown={(event) => {
        const target = event.target as HTMLElement;
        if (event.button === 0 && event.detail === 1 && !target.closest("button")) {
          startDragging();
        }
      }}
      onDoubleClick={(event) => {
        const target = event.target as HTMLElement;
        if (!target.closest("button")) toggleMaximize();
      }}
    >
      <div className="title-bar-brand" data-tauri-drag-region>
        <img src="/assets/app.png" alt="" aria-hidden="true" />
        <span>MemoPaws</span>
      </div>
      <div className="title-bar-controls">
        <button type="button" aria-label="最小化" title="最小化" onClick={minimize}>
          <img src="/assets/icons/minimize.svg" alt="" aria-hidden="true" />
        </button>
        <button type="button" aria-label={maximized ? "还原" : "最大化"} title={maximized ? "还原" : "最大化"} onClick={toggleMaximize}>
          <img src={`/assets/icons/${maximized ? "restore" : "maximize"}.svg`} alt="" aria-hidden="true" />
        </button>
        <button className="title-bar-close" type="button" aria-label="关闭" title="关闭" onClick={close}>
          <img src="/assets/icons/close.svg" alt="" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
