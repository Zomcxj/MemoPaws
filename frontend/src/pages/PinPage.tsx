import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { currentMonitor, getCurrentWindow, PhysicalSize } from "@tauri-apps/api/window";

// Pin window: shows a screenshot fragment, left-drag to move, wheel to zoom proportionally; the × in
// the top-right, right-click or Esc closes only this instance.
// The corner radius is decided before the screenshot and not adjustable here; the wheel only changes
// the window display size, never the original image pixels.
export function PinPage() {
  const [url, setUrl] = useState("");
  const [radius, setRadius] = useState(12);
  const [error, setError] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const resizeQueue = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    void invoke<[number[], number]>("get_pinned_image").then(([bytes, r]) => {
      if (!active || !bytes?.length) return;
      setRadius(r);
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, []);

  // Proportional wheel zoom: requests are serialized to avoid reordering, the ratio always comes from
  // the image's natural size, and is clamped by the current monitor's work area and a minimum of 32
  // physical pixels.
  const enqueueResize = (multiplier: number) => {
    resizeQueue.current = resizeQueue.current.then(async () => {
      const win = getCurrentWindow();
      const image = imageRef.current;
      if (!image?.naturalWidth || !image.naturalHeight) return;
      const [size, factor, monitor] = await Promise.all([win.innerSize(), win.scaleFactor(), currentMonitor()]);
      if (!monitor || !size.width || !size.height) return;
      const area = monitor.workArea;
      const position = await win.outerPosition();
      const maxW = Math.max(1, area.position.x + area.size.width - Math.max(position.x, area.position.x));
      const maxH = Math.max(1, area.position.y + area.size.height - Math.max(position.y, area.position.y));
      const upper = Math.min(maxW / image.naturalWidth, maxH / image.naturalHeight);
      const lower = Math.min(upper, Math.max((32 * factor) / image.naturalWidth, (32 * factor) / image.naturalHeight));
      const scale = Math.min(upper, Math.max(lower, (size.width / image.naturalWidth) * multiplier));
      await win.setSize(new PhysicalSize(Math.max(1, Math.round(image.naturalWidth * scale)), Math.max(1, Math.round(image.naturalHeight * scale))));
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  };

  // The listener must re-attach once the container renders (it only exists after the url is ready).
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const multiplier = event.deltaY < 0 ? 1.1 : event.deltaY > 0 ? 1 / 1.1 : 0;
      if (multiplier) enqueueResize(multiplier);
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [url]);

  // Ratio correction after system scaling or non-proportional resizes; deviations ≤1 physical pixel
  // are left alone to avoid a feedback loop with our own setSize. Listeners unregister on unmount
  // (including late registrations).
  useEffect(() => {
    const win = getCurrentWindow();
    let stopped = false;
    const stops: Array<() => void> = [];
    const track = (registration: Promise<() => void>) => {
      void registration.then((stop) => {
        if (stopped) stop();
        else stops.push(stop);
      }).catch(() => {});
    };
    const correct = async () => {
      const image = imageRef.current;
      if (!image?.naturalWidth || !image.naturalHeight) return;
      try {
        const size = await win.innerSize();
        if (size.width <= 0 || size.height <= 0) return;
        const expected = Math.round(size.width * (image.naturalHeight / image.naturalWidth));
        if (Math.abs(expected - size.height) <= 1) return;
        await win.setSize(new PhysicalSize(size.width, expected));
      } catch {
        // Correction failures do not affect the pin display.
      }
    };
    track(win.onScaleChanged(() => { void correct(); }));
    track(win.onResized(() => { void correct(); }));
    return () => {
      stopped = true;
      stops.forEach((stop) => stop());
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") void invoke("pin_close").catch(() => {});
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onMouseDown = (event: React.MouseEvent) => {
    if (event.button !== 0) return;
    if ((event.target as HTMLElement).closest("button")) return;
    event.preventDefault();
    void getCurrentWindow().startDragging().catch((reason) => {
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  };

  if (error) return <div style={{ background: "transparent", color: "#f2a2a2", height: "100vh", display: "grid", placeItems: "center", fontSize: 12, padding: 8 }}>{error}</div>;
  if (!url) return <div style={{ background: "transparent", color: "#888", height: "100vh", display: "grid", placeItems: "center" }}>加载中…</div>;
  return (
    <div
      ref={containerRef}
      data-pin-root=""
      style={{ width: "100vw", height: "100vh", overflow: "hidden", background: "transparent" }}
      onMouseDown={onMouseDown}
      onContextMenu={(e) => { e.preventDefault(); void invoke("pin_close").catch(() => {}); }}
    >
      <img ref={imageRef} src={url} alt="pinned" draggable={false} style={{ width: "100%", height: "100%", objectFit: "fill", display: "block", background: "transparent", borderRadius: radius, cursor: "default" }} />
      <button
        type="button"
        aria-label="关闭钉图"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={() => void invoke("pin_close").catch(() => {})}
        onContextMenu={(e) => e.stopPropagation()}
        style={{ position: "absolute", top: 4, right: 4, width: 22, height: 22, border: "none", borderRadius: "50%", background: "rgba(0,0,0,0.45)", color: "#fff", cursor: "pointer", padding: 0 }}
      >×</button>
    </div>
  );
}
