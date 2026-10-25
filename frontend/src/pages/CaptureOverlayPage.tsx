import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { asLang, type Lang } from "../i18n/lang";
import { CaptureOverlay, type RegionCss } from "../components/CaptureOverlay";
import { composePng } from "../annotation/render";
import type { Mark } from "../annotation/model";
import { copy } from "./RecognizePage";
import "./RecognizePage.css";

interface TextResult { text: string }
interface LocalLanguages { languages: { tag: string; name: string }[]; preferred: string }
// The capture overlay lives in its OWN frameless always-on-top window (the
// WeChat/Quark/Windows-snipping architecture): the main window stays hidden for
// the whole session and never participates, so a main-UI flash is structurally
// impossible — there is no fullscreen dance, no saved placement, nothing to
// restore. The window is PRE-CREATED at startup and reused for every capture:
// this page is the entire overlay app — it fetches the screenshot from the Rust
// session store, hosts CaptureOverlay, and every action either hits a backend
// command or ends the session (capture_overlay_end), which hides this window
// (kept warm) and restores the main window when the session semantics say so.
export function CaptureOverlayPage() {
  const [language, setLanguage] = useState<Lang>("zh");
  const [background, setBackground] = useState("");
  const [localLanguages, setLocalLanguages] = useState<LocalLanguages>({ languages: [], preferred: "" });
  const [localLanguage, setLocalLanguage] = useState("");
  const screenshotRef = useRef<HTMLImageElement | null>(null);
  const t = copy[language];
  const lastGeneration = useRef(0);
  const loadInFlight = useRef(false);
  // The overlay window is reused across sessions, so CaptureOverlay must REMOUNT
  // per session or the previous session's selection/marks/result state would
  // bleed into the next capture. The key bumps on every loaded image.
  const [session, setSession] = useState(0);

  useEffect(() => {
    let active = true;
    void invoke<Record<string, unknown>>("get_config").then((raw) => {
      if (active) setLanguage(asLang(raw.language));
    }).catch(() => {});
    // The window is PRE-CREATED at startup and reused: each session pushes a
    // "capture-image" event; a proactive fetch covers the very first session (the
    // event may fire before this listener attaches). Failures are ignored — no
    // image means nothing painted (the window stays transparent) and the Rust
    // 3s fallback cancels a stuck session.
    const loadFlow = async () => {
      if (loadInFlight.current) return;
      loadInFlight.current = true;
      try {
        const result = await invoke<ArrayBuffer | number[]>("capture_overlay_image");
        if (!active) return;
        const bytes = result instanceof ArrayBuffer ? new Uint8Array(result) : new Uint8Array(result);
        const screenshot = new Image();
        screenshot.src = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
        screenshotRef.current = screenshot;
        // Decode usually resolves in tens of milliseconds; a hidden window may
        // defer it, so race a short timeout — the transparent window makes any
        // not-yet-decoded frame desktop-through rather than white or black.
        await Promise.race([screenshot.decode(), new Promise((resolve) => setTimeout(resolve, 250))]);
        if (!active) return;
        setBackground(screenshot.src);
        setSession((current) => current + 1);
      } catch {
        // Startup probe without an active session: stay transparent and wait.
      } finally {
        loadInFlight.current = false;
      }
    };
    void loadFlow();
    const unlistenImage = listen("capture-image", () => { void loadFlow(); });
    // Events to HIDDEN pages cannot be trusted (WebView2 throttles them): poll
    // the session generation as the reliable transport. The event stays as a
    // fast path.
    const generationTimer = setInterval(() => {
      void invoke<number>("capture_overlay_generation").then((generation) => {
        if (generation !== lastGeneration.current) {
          lastGeneration.current = generation;
          void loadFlow();
        }
      }).catch(() => {});
    }, 120);
    void invoke<LocalLanguages>("local_ocr_languages").then((result) => {
      if (!active) return;
      setLocalLanguages(result);
      setLocalLanguage(result.preferred || result.languages[0]?.tag || "");
    }).catch(() => {});
    return () => { active = false; clearInterval(generationTimer); void unlistenImage.then((stop: () => void) => stop()); };
  }, []);
  // Reveal the window only AFTER React has committed the fresh per-session
  // CaptureOverlay (the key bump above): invoking ready directly from loadFlow
  // could show the window while the previous session's DOM was still mounted.
  useEffect(() => {
    if (session > 0) void invoke("capture_overlay_ready").catch(() => {});
  }, [session]);

  // Ends the session (Rust hides this window — kept warm — and restores the main
  // window when the outcome says so, revealing a pin after the screen is clean).
  // CRITICAL ORDER: the painted state is cleared BEFORE the hide, so the last
  // composited frame is transparent. A hidden window keeps presenting its cached
  // frame when re-shown — without this, the next capture would flash this
  // session's stale selection for a frame or two.
  // A full-screen PNG as a JSON array is tens of millions of IPC elements and
  // wedges the overlay (the black-canvas lockup): images travel as base64.
  const bytesToBase64 = (bytes: Uint8Array) => {
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  };
  const endSession = (outcome: "pin" | "confirm" | "cancel", revealPin: string | null, result?: { image: Uint8Array; ocrText: string; translation: string }) => {
    setBackground("");
    screenshotRef.current = null;
    return new Promise((resolve) => setTimeout(resolve, 60))
      .then(() => invoke("capture_overlay_end", {
        outcome,
        revealPin,
        ocrText: result ? result.ocrText : null,
        translation: result ? result.translation : null,
        imageBase64: result ? bytesToBase64(result.image) : null,
      }))
      // Belt-and-suspenders: capture_overlay_end already hid this window and
      // settled the session synchronously; this only covers a survivor.
      .then(() => { void invoke("capture_overlay_finish").catch(() => {}); });
  };

  const cropFromImage = async (region: RegionCss, scale: number, cornerRadius?: number, marks: Mark[] = []): Promise<Uint8Array> => {
    const screenshot = screenshotRef.current;
    if (!screenshot) throw new Error(t.needImage);
    return composePng(screenshot, region, scale || window.devicePixelRatio || 1, cornerRadius || 0, marks);
  };
  const recognize = async (marked: Uint8Array) => {
    const result = await invoke<TextResult>("ai_ocr", { image: Array.from(marked), keyEntryId: null });
    return result.text || "(无识别结果)";
  };
  const translate = async (marked: Uint8Array) => {
    const ocr = await invoke<TextResult>("ai_ocr", { image: Array.from(marked), keyEntryId: null });
    const tr = await invoke<TextResult>("ai_translate", { text: ocr.text, target: "en", source: "zh", keyEntryId: null });
    return { ocrText: ocr.text, translation: tr.text || "(翻译失败)" };
  };
  const localRecognize = async (marked: Uint8Array) => {
    const result = await invoke<TextResult>("local_ocr", { image: Array.from(marked), language: localLanguage });
    return result.text || "(无识别结果)";
  };
  const confirmCapture = async (result: { image: Uint8Array; ocrText: string; translation: string }) => {
    // Hand the result to Rust (the hidden main window polls it — events to
    // hidden pages cannot be trusted), then end the session.
    await endSession("confirm", null, result);
  };
  const pinImage = async (marked: Uint8Array, cornerRadius: number) => {
    // The pin is created hidden; capture_overlay_end closes this overlay (clean
    // desktop) and only then reveals the pin — "everything exits, then the pin
    // appears".
    // The composed image MUST travel base64: as a JSON array (millions of
    // elements) it got corrupted, and the pin window showed an image that never
    // decoded (naturalWidth=0 - "pin did not appear").
    const label = await invoke<string>("pin_image", { imageBase64: bytesToBase64(marked), radius: cornerRadius });
    await endSession("pin", label);
  };
  const copyImage = async (marked: Uint8Array) => {
    const blob = new Blob([marked.slice()], { type: "image/png" });
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
  };
  const saveImage = async (marked: Uint8Array) => {
    await invoke<string | null>("save_image_as", { image: Array.from(marked) });
  };

  if (!background) {
    // Nothing until the screenshot is ready: the first frames are pure black
    // (window background), never app UI.
    return <div style={{ width: "100vw", height: "100vh", background: "transparent" }} />;
  }
  return <div data-overlay-session={session}>
    <CaptureOverlay
      key={session}
    background={background}
    hint={t.overlay}
    onConfirm={confirmCapture}
    onCrop={cropFromImage}
    onCancel={() => { void endSession("cancel", null); }}
    onRecognize={recognize}
    onTranslate={translate}
    onLocalRecognize={localRecognize}
    localLanguages={localLanguages.languages}
    localLanguage={localLanguage}
    onLocalLanguageChange={setLocalLanguage}
    onPinImage={pinImage}
    onCopyImage={copyImage}
    onSaveImage={saveImage}
    labels={{ recognize: t.ocr, translate: t.translate, copyImage: t.copyImage, saveImage: t.save, confirm: language === "zh" ? "确认" : "Confirm", cancel: t.close, copied: t.copied, colorHint: language === "zh" ? "按 C 复制 HEX" : "Press C to copy HEX", resize: language === "zh" ? "调整结果窗口大小" : "Resize result window", toolMove: t.toolMove, toolArrow: t.toolArrow, toolRectangle: t.toolRectangle, toolPen: t.toolPen, toolText: t.toolText, toolMosaic: t.mosaic, strokeColor: t.strokeColor, strokeWidth: t.strokeWidth, undo: t.undo, redo: t.redo, textCommit: t.textCommit, textCancel: t.textCancel, localOcr: t.localOcr, localOcrLanguage: t.localOcrLanguage }}
    />
  </div>;
}
