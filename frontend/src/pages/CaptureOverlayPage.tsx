import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { asLang, type Lang } from "../i18n/lang";
import { CaptureOverlay, type RegionCss } from "../components/CaptureOverlay";
import { composePng } from "../annotation/render";
import type { Mark } from "../annotation/model";
import { copy } from "./RecognizePage";
import { decodeQrImage } from "../utils/qr";
import "./RecognizePage.css";

interface TextResult { text: string }
interface LocalLanguages { languages: { tag: string; name: string }[]; preferred: string }

// The capture overlay is its OWN frameless always-on-top window and runs in
// LIVE-SCREEN mode (the Windows-snipping / Verta architecture): the screen below
// stays live and nothing disturbs it — the main window is not hidden and no frame
// is grabbed to paint with. Pixels are grabbed only when an action needs them
// (recognize / translate / save / pin / confirm), and those pixels are what the
// user saw: the app's own window included, because nothing moved it.
//
// A session arms through capture_overlay_show (Rust shows this window and emits
// "capture-image"); this page answers by grabbing ONE frame for the loupe and
// colour picker — a grab reads pixels and changes nothing on screen.
type Mode = "idle" | "live" | "ending";

export function CaptureOverlayPage() {
  const [language, setLanguage] = useState<Lang>("zh");
  const [localLanguages, setLocalLanguages] = useState<LocalLanguages>({ languages: [], preferred: "" });
  const [localLanguage, setLocalLanguage] = useState("");
  const [mode, setMode] = useState<Mode>("idle");
  const sampleRef = useRef<HTMLCanvasElement | null>(null);
  const t = copy[language];
  const lastGeneration = useRef(0);
  const loadInFlight = useRef(false);
  // The event and the generation poll both announce one arming; dedupe by
  // generation so the second signal cannot remount CaptureOverlay and wipe a
  // selection the user just made.
  const armedGeneration = useRef(-1);
  // The window is reused across sessions, so CaptureOverlay must REMOUNT per
  // session or the previous session's selection/marks/result state would bleed
  // into the next capture. The key bumps on every arm.
  const [session, setSession] = useState(0);

  useEffect(() => {
    let active = true;
    void invoke<Record<string, unknown>>("get_config").then((raw) => {
      if (active) setLanguage(asLang(raw.language));
    }).catch(() => {});
    // One grab per arm, for the loupe/colour picker only: the overlay paints
    // nothing from it (the screen below is live and unstyled).
    const armSession = async () => {
      if (loadInFlight.current) return;
      loadInFlight.current = true;
      let armed = false;
      try {
        const generation = await invoke<number>("capture_overlay_generation").catch(() => 0);
        if (generation === armedGeneration.current) return;
        armedGeneration.current = generation;
        armed = true;
        const displayIndex = await invoke<number | null>("capture_overlay_display_index").catch(() => null);
        const bytes = await invoke<ArrayBuffer | number[]>("capture_screen", { displayIndex: displayIndex ?? undefined });
        if (!active) return;
        const png = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : new Uint8Array(bytes);
        const bitmap = await createImageBitmap(new Blob([png], { type: "image/png" })).catch(() => null);
        if (bitmap) {
          const canvas = document.createElement("canvas");
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
          canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
          bitmap.close();
          sampleRef.current = canvas;
        }
      } catch {
        // A failed loupe grab must not block the session: the overlay still works,
        // only the magnifier stays empty.
      } finally {
        if (active && armed) {
          setSession((current) => current + 1);
          setMode("live");
        }
        loadInFlight.current = false;
      }
    };
    const unlistenImage = listen("capture-image", () => { void armSession(); });
    // Events to HIDDEN pages cannot be trusted (WebView2 throttles them): poll
    // the session generation as the reliable transport. The event stays as a
    // fast path. The generation only advances when a session STARTS; armSession
    // dedupes by generation, so both signals together arm exactly once.
    const generationTimer = setInterval(() => {
      void invoke<number>("capture_overlay_generation").then((generation) => {
        if (generation !== lastGeneration.current) {
          lastGeneration.current = generation;
          void armSession();
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
  // The arming handshake stays explicit (a no-op once the window is already up).
  useEffect(() => {
    if (mode === "live") void invoke("capture_overlay_ready").catch(() => {});
  }, [mode, session]);

  // Ends the session (Rust hides this window and settles the session).
  // CRITICAL ORDER: nothing is painted for the brief moment before the hide, so
  // the last composited frame is transparent — a hidden window keeps presenting
  // its cached frame when re-shown, and a stale selection would flash.
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
    setMode("ending");
    sampleRef.current = null;
    return new Promise((resolve) => setTimeout(resolve, 60))
      .then(() => invoke<{ restored: boolean; generation: number }>("capture_overlay_end", {
        outcome,
        revealPin,
        ocrText: result ? result.ocrText : null,
        translation: result ? result.translation : null,
        imageBase64: result ? bytesToBase64(result.image) : null,
      }))
      .then((end) => {
        // The window is hidden by now: back to idle unseen — unless a new session
        // already armed this page (rapid back-to-back captures), in which case the
        // late idle would blank the overlay the user is already looking at.
        setMode((current) => (current === "ending" ? "idle" : current));
        return invoke("capture_overlay_finish", { generation: end.generation }).catch(() => {});
      });
  };

  // The one seam every action goes through: grab the screen NOW, crop the
  // selection, compose the marks. In live-screen mode there is no pre-taken frame
  // to crop from — the grab happens here, which is exactly why the app never
  // disturbs the screen to take a picture of it.
  const cropFromImage = async (region: RegionCss, scale: number, cornerRadius?: number, marks: Mark[] = []): Promise<Uint8Array> => {
    const displayIndex = await invoke<number | null>("capture_overlay_display_index").catch(() => null);
    const bytes = await invoke<ArrayBuffer | number[]>("capture_screen", { displayIndex: displayIndex ?? undefined });
    const png = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : new Uint8Array(bytes);
    const url = URL.createObjectURL(new Blob([png], { type: "image/png" }));
    try {
      const image = new Image();
      image.src = url;
      await image.decode().catch(() => {});
      return await composePng(image, region, scale || window.devicePixelRatio || 1, cornerRadius || 0, marks);
    } finally {
      URL.revokeObjectURL(url);
    }
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
  const qrRecognize = async (marked: Uint8Array) => decodeQrImage(marked);
  const confirmCapture = async (result: { image: Uint8Array; ocrText: string; translation: string }) => {
    // Hand the result to Rust (the main window polls it — events to hidden pages
    // cannot be trusted), then end the session.
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

  if (mode === "idle") {
    // Idle: the window is normally hidden, so this is only the first frame the
    // NEXT session shows. Same 25% tone the live overlay paints, so the swap from
    // veil to overlay has no brightness step at all.
    return <div className="capture-overlay-veil" />;
  }
  if (mode === "ending") {
    // Nothing painted for the moment before Rust hides the window: the cached
    // frame must be transparent (see endSession).
    return null;
  }
  return <div data-overlay-session={session}>
    <CaptureOverlay
      key={session}
    sampleCanvas={sampleRef}
    hint={t.overlay}
    onConfirm={confirmCapture}
    onCrop={cropFromImage}
    onCancel={() => { void endSession("cancel", null); }}
    onRecognize={recognize}
    onTranslate={translate}
    onLocalRecognize={localRecognize}
    onQr={qrRecognize}
    localLanguages={localLanguages.languages}
    localLanguage={localLanguage}
    onLocalLanguageChange={setLocalLanguage}
    onPinImage={pinImage}
    onCopyImage={copyImage}
    onSaveImage={saveImage}
    labels={{ recognize: t.ocr, translate: t.translate, copyImage: t.copyImage, saveImage: t.save, confirm: language === "zh" ? "确认" : "Confirm", cancel: t.close, copied: t.copied, colorHint: language === "zh" ? "按 C 复制 HEX" : "Press C to copy HEX", resize: language === "zh" ? "调整结果窗口大小" : "Resize result window", toolMove: t.toolMove, toolArrow: t.toolArrow, toolRectangle: t.toolRectangle, toolPen: t.toolPen, toolText: t.toolText, toolMosaic: t.mosaic, strokeColor: t.strokeColor, strokeWidth: t.strokeWidth, undo: t.undo, redo: t.redo, textCommit: t.textCommit, textCancel: t.textCancel, localOcr: t.localOcr, localOcrLanguage: t.localOcrLanguage, qr: t.qr, qrEmpty: t.qrEmpty }}
    />
  </div>;
}
