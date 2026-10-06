import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

// 钉图窗口：显示截图片段，右上角×关闭，drag。圆角在截图前已确定，这里不接受调整。
export function PinPage() {
  const [url, setUrl] = useState("");
  const [radius, setRadius] = useState(12);
  useEffect(() => {
    let active = true;
    void invoke<[number[], number]>("get_pinned_image").then(([bytes, r]) => {
      if (!active || !bytes?.length) return;
      setRadius(r);
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      setUrl(URL.createObjectURL(blob));
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") void invoke("pin_close");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!url) return <div style={{ background: "transparent", color: "#888", height: "100vh", display: "grid", placeItems: "center" }}>加载中…</div>;
  return (
    <div style={{ width: "100vw", height: "100vh", overflow: "hidden", background: "transparent" }}>
      <img src={url} alt="pinned" style={{ width: "100%", height: "100%", objectFit: "fill", display: "block", background: "transparent", borderRadius: radius, WebkitAppRegion: "drag" } as React.CSSProperties} onContextMenu={(e) => { e.preventDefault(); void invoke("pin_close"); }} />
      <button type="button" onClick={() => void invoke("pin_close")} onContextMenu={(e) => e.stopPropagation()} style={{ position: "absolute", top: 4, right: 4, width: 22, height: 22, border: "none", borderRadius: "50%", background: "rgba(0,0,0,0.45)", color: "#fff", cursor: "pointer", padding: 0, WebkitAppRegion: "no-drag" } as React.CSSProperties}>×</button>
    </div>
  );
}
