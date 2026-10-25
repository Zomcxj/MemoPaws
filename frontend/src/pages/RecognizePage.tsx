import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import type { Lang } from "../i18n/lang";
import "./RecognizePage.css";

type OcrLanguage = "zh" | "en" | "ja" | "ko" | "fr" | "de" | "es" | "ru";
interface TextResult { text: string }
interface HistoryRecord { time: string; type: string; text: string; ocr_text?: string; translate_text?: string }
interface DisplayInfo { index: number; name: string; x: number; y: number; width: number; height: number; is_primary: boolean }

const languages: { value: OcrLanguage; label: string }[] = [
  { value: "zh", label: "中文" }, { value: "en", label: "English" }, { value: "ja", label: "日本語" },
  { value: "ko", label: "한국어" }, { value: "fr", label: "Français" }, { value: "de", label: "Deutsch" },
  { value: "es", label: "Español" }, { value: "ru", label: "Русский" },
];
export const copy = {
  zh: { import: "导入", capture: "截图", gray: "灰度", binary: "二值化", mosaic: "马赛克", reset: "重置", clear: "清空", save: "保存图片", processing: "处理中...", punch: "One Punch", close: "关闭", empty: "导入图片开始识别", history: "操作历史", emptyHistory: "暂无成功记录", ocr: "AI识别", translate: "AI翻译", needImage: "请先导入图片", needKey: "请先添加 LLM 密钥", needText: "没有可翻译文本", file: "请选择图片文件", large: "图片不能超过 25 MiB", crop: "拖拽选择裁剪区域", overlay: "拖拽框选截图区域", clearHistory: "清空全部历史？", copy: "复制", copied: "已复制", clearText: "清空文本", copyFailed: "复制失败，请检查剪贴板权限", display: "显示器", copyImage: "复制图片", pasteImage: "粘贴图片", contextCopyImage: "复制图片", contextPasteImage: "粘贴图片", contextCopyText: "复制识别文本", contextSave: "保存图片", contextReset: "重置", historyDelete: "删除", historyClear: "清空", historyHide: "收起", historyShow: "展开", historyLoad: "载入画布", historyNoImage: "该记录无图片，已回填文本", toolMove: "移动", toolArrow: "箭头", toolRectangle: "矩形", toolPen: "画笔", toolText: "文字", strokeColor: "线条颜色", strokeWidth: "线宽", undo: "撤销", redo: "重做", textCommit: "提交文字", textCancel: "取消文字", localOcr: "离线 OCR", localOcrLanguage: "离线 OCR 语言", localOcrEmpty: "未识别到文字", localOcrUnavailable: "未检测到已安装的离线 OCR 语言" },
  en: { import: "Import", capture: "Capture", gray: "Gray", binary: "Binary", mosaic: "Mosaic", reset: "Reset", clear: "Clear", save: "Save image", processing: "Working...", punch: "One Punch", close: "Close", empty: "Import an image to start", history: "History", emptyHistory: "No records yet", ocr: "AI OCR", translate: "AI Translate", needImage: "Import an image first", needKey: "Add an LLM key first", needText: "No text to translate", file: "Choose an image file", large: "Image must be under 25 MiB", crop: "Drag to select crop", overlay: "Drag to select a capture region", clearHistory: "Clear all history?", copy: "Copy", copied: "Copied", clearText: "Clear text", copyFailed: "Copy failed. Check clipboard permissions", display: "Display", copyImage: "Copy image", pasteImage: "Paste image", contextCopyImage: "Copy image", contextPasteImage: "Paste image", contextCopyText: "Copy recognized text", contextSave: "Save image", contextReset: "Reset", historyDelete: "Delete", historyClear: "Clear all", historyHide: "Collapse", historyShow: "Expand", historyLoad: "Load to canvas", historyNoImage: "No image in record, text restored", toolMove: "Move", toolArrow: "Arrow", toolRectangle: "Rectangle", toolPen: "Pen", toolText: "Text", strokeColor: "Stroke color", strokeWidth: "Stroke width", undo: "Undo", redo: "Redo", textCommit: "Commit text", textCancel: "Discard text", localOcr: "Offline OCR", localOcrLanguage: "Offline OCR language", localOcrEmpty: "No text recognized", localOcrUnavailable: "No installed offline OCR languages detected" },
} as const;
const MAX_IMAGE_BYTES = 25 * 1024 * 1024;
const errorText = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

interface ContextMenuState { x: number; y: number }

// Query result of installed offline OCR languages (the local_ocr_languages command response).
interface LocalLanguages { languages: { tag: string; name: string }[]; preferred: string }

export function RecognizePage({ language = "zh" }: { language?: Lang }) {
  const t = copy[language];
  const [image, setImage] = useState<Uint8Array | null>(null);
  const [preview, setPreview] = useState("");
  const [original, setOriginal] = useState<Uint8Array | null>(null);
  const [ocrText, setOcrText] = useState("");
  const [translation, setTranslation] = useState("");
  const [source, setSource] = useState<OcrLanguage>("zh");
  const [target, setTarget] = useState<OcrLanguage>("en");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedTranslation, setCopiedTranslation] = useState(false);
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [past, setPast] = useState<Uint8Array[]>([]);
  const [future, setFuture] = useState<Uint8Array[]>([]);
  const [displays, setDisplays] = useState<DisplayInfo[]>([]);
  const [selectedDisplay, setSelectedDisplay] = useState(0);
  

  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef(preview);
  const captureSessionStartedRef = useRef(false);
  const captureRef = useRef<() => void>(() => {});

  const urlFor = (bytes: Uint8Array) => URL.createObjectURL(new Blob([bytes.slice()], { type: "image/png" }));
  // Offline OCR operation token: image changes, new main OCR requests and unmount all invalidate pending offline results.
  const localOperation = useRef(0);
  const setBytes = (bytes: Uint8Array, keepHistory = true) => {
    localOperation.current += 1;
    if (keepHistory && image) setPast((items) => [...items, image]);
    setFuture([]); setImage(new Uint8Array(bytes));
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const url = urlFor(bytes); previewRef.current = url; setPreview(url);
  };
  const [localLanguages, setLocalLanguages] = useState<LocalLanguages>({ languages: [], preferred: "" });
  const [localLanguage, setLocalLanguage] = useState("");

  const importFile = async (file: File) => {
    if (!file.type.startsWith("image/")) { setError(t.file); return; }
    if (file.size > MAX_IMAGE_BYTES) { setError(t.large); return; }
    const bytes = new Uint8Array(await file.arrayBuffer()); setOriginal(new Uint8Array(bytes)); setBytes(bytes, false);
    setOcrText(""); setTranslation(""); setError("");
  };
  const importImage = (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void importFile(file); };
  const dropImage = (event: DragEvent<HTMLElement>) => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) void importFile(file); };
  // History actions.
  const formatTime = (raw: string) => {
    const stamp = Number(raw);
    if (!raw || !Number.isFinite(stamp) || stamp <= 0) return raw;
    return new Date(stamp * 1000).toLocaleString("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  };
  const deleteHistory = (index: number) => void run(async () => { await invoke("history_delete", { index }); setHistory((await invoke<HistoryRecord[]>("history_list"))); });
  const clearAllHistory = () => { if (!window.confirm(t.clearHistory)) return; void run(async () => { await invoke("history_clear"); setHistory([]); }); };
  const loadHistory = (record: HistoryRecord) => {
    // HistoryRecord has no image field; restore text only and inform the user.
    setOcrText(record.ocr_text || ""); setTranslation(record.translate_text || "");
    setError(t.historyNoImage);
  };

  const config = () => ({ keyEntryId: null });
  const run = async (operation: () => Promise<void>) => { setLoading(true); setError(""); try { await operation(); } catch (reason) { setError(errorText(reason)); } finally { setLoading(false); } };
  const recognize = () => { localOperation.current += 1; void run(async () => { if (!image) throw new Error(t.needImage); setRecognizing(true); try { const result = await invoke<TextResult>("ai_ocr", { image: Array.from(image), ...config() }); setOcrText(result.text); setTranslation(""); } finally { setRecognizing(false); } }); };
  const translate = () => void run(async () => { if (!ocrText.trim()) throw new Error(t.needText); setTranslating(true); try { const result = await invoke<TextResult>("ai_translate", { text: ocrText, target, source, ...config() }); setTranslation(result.text); } finally { setTranslating(false); } });
  const onePunch = () => { localOperation.current += 1; void run(async () => { if (!image) throw new Error(t.needImage); const result = await invoke<TextResult>("ai_ocr", { image: Array.from(image), ...config() }); setOcrText(result.text); const translated = await invoke<TextResult>("ai_translate", { text: result.text, target, source, ...config() }); setTranslation(translated.text); }); };
  // Offline OCR: current image bytes + currently selected language; no fill when the token is stale or
  // the image changed. Nonempty success clears the stale translation; empty success reports
  // "未识别到文字" without overwriting existing content.
  const localRecognize = () => {
    if (!localLanguages.languages.length || !localLanguage) return;
    const token = ++localOperation.current;
    void run(async () => {
      if (!image) throw new Error(t.needImage);
      const result = await invoke<TextResult>("local_ocr", { image: Array.from(image), language: localLanguage });
      if (localOperation.current !== token) return;
      if (result.text.trim()) { setOcrText(result.text); setTranslation(""); }
      else setError(t.localOcrEmpty);
    });
  };
  const preprocess = (mode: "gray" | "binary" | "mosaic") => void run(async () => { if (!image) throw new Error(t.needImage); const result = await invoke<{ image: number[] }>("image_preprocess", { image: Array.from(image), mode }); setBytes(new Uint8Array(result.image)); });
  const undo = () => { const previous = past[past.length - 1]; if (!previous || !image) return; setPast((items) => items.slice(0, -1)); setFuture((items) => [...items, image]); setBytes(previous, false); };
  const redo = () => { const next = future[future.length - 1]; if (!next || !image) return; setFuture((items) => items.slice(0, -1)); setPast((items) => [...items, image]); setBytes(next, false); };
  const reset = () => { if (original) setBytes(original); };
  const clear = () => { localOperation.current += 1; setImage(null); setOriginal(null); setPreview(""); setOcrText(""); setTranslation(""); setPast([]); setFuture([]); };
  const copyOcrText = async () => { if (!ocrText) return; try { await navigator.clipboard.writeText(ocrText); setCopied(true); window.setTimeout(() => setCopied(false), 1500); } catch { setError(t.copyFailed); } };
  const copyTranslation = async () => { if (!translation) return; try { await navigator.clipboard.writeText(translation); setCopiedTranslation(true); window.setTimeout(() => setCopiedTranslation(false), 1500); } catch { setError(t.copyFailed); } };
  const clearOcrText = () => { setOcrText(""); setTranslation(""); setError(""); };
  const capture = async () => {
    if (captureSessionStartedRef.current) return;
    setError("");
    try {
      const window = getCurrentWindow();
      // The session registers before hiding: Rust records whether the main window was visible before the capture began.
      await invoke("capture_session_begin", { visible: await window.isVisible() });
      captureSessionStartedRef.current = true;
      // The overlay is a separate frameless window now: the main window just hides
      // and never participates in the session — no geometry dance, no fullscreen,
      // nothing that could ever flash the app UI back on screen.
      await window.hide();
      // Wait for the Windows compositor to finish the hide animation, otherwise the main window leaves a ghost in the screenshot.
      await new Promise((resolve) => setTimeout(resolve, 320));
      const display = displays.find((item) => item.index === selectedDisplay);
      const bytes = await invoke<ArrayBuffer | number[]>("capture_screen", { displayIndex: displays.length > 1 ? selectedDisplay : undefined });
      const png = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : new Uint8Array(bytes);
      await invoke("capture_overlay_begin", {
        png: Array.from(png),
        display: display ? { x: display.x, y: display.y, width: display.width, height: display.height } : null,
      });
    } catch (reason) {
      // No overlay window exists on this path: end the session and come back.
      captureSessionStartedRef.current = false;
      try { await invoke("capture_session_finish", { outcome: "cancel" }); } catch { /* keep the first error */ }
      try { await getCurrentWindow().show(); } catch { /* nothing more we can do */ }
      setError(errorText(reason));
    }
  };

  captureRef.current = () => { void capture(); };
  const exportImageBytes = (bytes: Uint8Array) => {
    return invoke<string | null>("save_image_as", { image: Array.from(bytes) });
  };
  const exportImage = () => { if (image) void run(async () => { await exportImageBytes(image); }); };
  const onContextMenu = (event: React.MouseEvent) => {
    if (!image) return;
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY });
  };
  const closeContextMenu = () => setContextMenu(null);
  const contextCopyImage = () => { closeContextMenu(); void run(async () => { if (!image) return; const blob = new Blob([image.slice()], { type: "image/png" }); await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]); }); };
  const contextPasteImage = () => { closeContextMenu(); void run(async () => { try { const items = await navigator.clipboard.read(); for (const item of items) { const type = item.types.find((t) => t.startsWith("image/")); if (!type) continue; const blob = await item.getType(type); const bytes = new Uint8Array(await blob.arrayBuffer()); setOriginal(bytes); setBytes(bytes, false); setOcrText(""); setTranslation(""); setError(""); return; } } catch { setError(t.copyFailed); } }); };
  const contextCopyText = () => { closeContextMenu(); void copyOcrText(); };
  const contextSave = () => { closeContextMenu(); void exportImage(); };
  const contextReset = () => { closeContextMenu(); reset(); };

  useEffect(() => { let active = true; Promise.all([invoke<HistoryRecord[]>("history_list"), invoke<DisplayInfo[]>("list_displays").catch(() => [] as DisplayInfo[])]).then(([records, disp]) => { if (active) { setHistory(records); setDisplays(disp); const primary = disp.findIndex((d) => d.is_primary); setSelectedDisplay(primary >= 0 ? primary : 0); if ((window as unknown as { __memoPendingCapture?: boolean }).__memoPendingCapture) { (window as unknown as { __memoPendingCapture?: boolean }).__memoPendingCapture = false; // Wait for the new page to finish painting before hiding: hiding right after mount stretches the DWM hide transition, and a clean frame cannot be captured within 320ms (semi-transparent main-UI ghost).
requestAnimationFrame(() => requestAnimationFrame(() => captureRef.current())); } } }).catch((reason) => active && setError(errorText(reason))); return () => { active = false; if (previewRef.current) URL.revokeObjectURL(previewRef.current); }; }, []);
  // Offline OCR languages are queried exactly once: a failure shows the capability error without
  // breaking history/display initialization.
  useEffect(() => {
    let active = true;
    void invoke<LocalLanguages>("local_ocr_languages").then((result) => {
      if (!active) return;
      setLocalLanguages(result);
      setLocalLanguage(result.preferred || result.languages[0]?.tag || "");
    }).catch((reason) => { if (active) setError(errorText(reason)); });
    return () => { active = false; localOperation.current += 1; };
  }, []);
  useEffect(() => { const captureEvent = () => { (window as unknown as { __memoPendingCapture?: boolean }).__memoPendingCapture = false; captureRef.current(); }; const fitEvent = () => setZoom(1); const recognizeTextEvent = (event: Event) => { const text = (event as CustomEvent<{ text?: unknown }>).detail?.text; if (typeof text === "string") { setOcrText(text); setTranslation(""); setError(""); setCopied(false); } }; const recognizeImageEvent = (event: Event) => { const bytes = (event as CustomEvent<{ image?: unknown }>).detail?.image; if (!Array.isArray(bytes) || !bytes.every((byte) => typeof byte === "number")) return; setOriginal(new Uint8Array(bytes)); setBytes(new Uint8Array(bytes), false); setOcrText(""); setTranslation(""); setError(""); }; window.addEventListener("memopaws-capture", captureEvent); window.addEventListener("canvas_fit", fitEvent); window.addEventListener("recognize-text", recognizeTextEvent); window.addEventListener("recognize-image", recognizeImageEvent); return () => { window.removeEventListener("memopaws-capture", captureEvent); window.removeEventListener("canvas_fit", fitEvent); window.removeEventListener("recognize-text", recognizeTextEvent); window.removeEventListener("recognize-image", recognizeImageEvent); }; }, []);
  // While a capture session is in flight the main window is HIDDEN, and WebView2
  // event delivery to hidden pages cannot be trusted — so the session end AND
  // the confirmed result are polled from Rust state. (The "capture-ended" event
  // below stays as a fast path; this poll is the guarantee.)
  useEffect(() => {
    // The confirmed result must keep this poll alive: the "capture-ended" fast
    // path re-arms the guard the moment the overlay closes, and an
    // [sessionActive]-scoped timer would be torn down before the result (stored
    // in the same instant) is picked up — every confirmed image was lost that
    // way. This page lives as long as the app, so the timer always exists; it
    // is idle between sessions.
    let stopped = false;
    let seenResultGeneration = 0;
    const applyResult = (image: Uint8Array, ocrText: string, translation: string) => {
      setOriginal(image);
      setBytes(image, false);
      setOcrText(ocrText);
      setTranslation(translation);
      void invoke<HistoryRecord[]>("history_list").then((records) => setHistory(records)).catch(() => {});
    };
    const timer = setInterval(() => {
      void invoke<{ active: boolean; ocrText: string | null; translation: string | null; resultGeneration: number } | null>("capture_session_status").then((status) => {
        if (stopped || !status) return;
        if (status.ocrText !== null && status.resultGeneration > seenResultGeneration) {
          seenResultGeneration = status.resultGeneration;
          // The confirmed image travels over the binary channel (the JSON-array
          // form wedged the IPC).
          void invoke<ArrayBuffer | number[]>("capture_session_result_image").then((bytes) => {
            if (stopped) return;
            applyResult(bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : new Uint8Array(bytes), status.ocrText || "", status.translation || "");
          }).catch(() => {});
        }
        if (!status.active) {
          captureSessionStartedRef.current = false;
          void invoke<HistoryRecord[]>("history_list").then((records) => setHistory(records)).catch(() => {});
        }
      }).catch(() => {});
    }, 150);
    return () => { stopped = true; clearInterval(timer); };
  }, []);
  // Fast-path re-arm when the overlay session ends (the poll above is the
  // guaranteed path).
  useEffect(() => {
    const unlisten = listen("capture-ended", () => {
      captureSessionStartedRef.current = false;
    });
    return () => { void unlisten.then((stop) => stop()); };
  }, []);
  useEffect(() => { const onDocClick = () => closeContextMenu(); document.addEventListener("click", onDocClick); return () => document.removeEventListener("click", onDocClick); }, []);

  return <section className="recognize-page" onDragOver={(event) => event.preventDefault()} onDrop={dropImage}>
    <header className="recognize-toolbar"><div className="toolbar-actions">
      <label className="tool-button"><img src="/assets/icons/import.svg" alt="" />{t.import}<input type="file" accept="image/*" onChange={importImage} /></label>
      <button className="tool-button" onClick={() => void capture()}><img src="/assets/icons/capture.svg" alt="" />{t.capture}</button>
      {displays.length > 1 && <select className="tool-button" aria-label={t.display} value={selectedDisplay} onChange={(event) => setSelectedDisplay(Number(event.target.value))}>{displays.map((d) => <option key={d.index} value={d.index}>{d.name}{d.is_primary ? " (P)" : ""}</option>)}</select>}
      <button className="tool-button" disabled={!image || loading} onClick={() => preprocess("gray")}>{t.gray}</button>
      <button className="tool-button" disabled={!image || loading} onClick={() => preprocess("binary")}>{t.binary}</button>
      <button className="tool-button" disabled={!image || loading} onClick={() => preprocess("mosaic")}>{t.mosaic}</button>
      <button className="tool-button" disabled={!past.length} onClick={undo}>↶</button><button className="tool-button" disabled={!future.length} onClick={redo}>↷</button>
      <button className="tool-button" disabled={!image} onClick={() => setZoom((value) => Math.min(8, value * 1.25))}>+</button><button className="tool-button" disabled={!image} onClick={() => setZoom((value) => Math.max(.1, value / 1.25))}>-</button>
      <button className="tool-button" disabled={!original} onClick={reset}>{t.reset}</button><button className="tool-button" disabled={!image} onClick={clear}>{t.clear}</button><button className="tool-button" disabled={!image || loading} onClick={exportImage}>{t.save}</button>
    </div><button className="recognize-primary" disabled={!image || loading} onClick={onePunch}>{loading ? t.processing : t.punch}</button></header>
    {error && <div className="recognize-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>{t.close}</button></div>}
    <div className="recognize-workspace">
      <div className="recognize-left">
        <article className="recognize-panel image-panel" onContextMenu={onContextMenu}>
          {preview ? <>
            <div className="image-canvas" ref={canvasRef}>
              <img src={preview} alt={t.empty} style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }} draggable={false} />
            </div>
          </> : <div className="image-empty"><strong>{t.empty}</strong></div>}
        </article>
        <section className="recognize-history">
          <div className="history-head">
            <h2>{t.history}</h2>
            <div className="history-head-actions">
              {history.length > 0 && <button type="button" onClick={clearAllHistory}>{t.historyClear}</button>}
              <button type="button" className="history-toggle" onClick={() => setHistoryOpen((value) => !value)} aria-expanded={historyOpen}>{historyOpen ? t.historyHide : t.historyShow}</button>
            </div>
          </div>
          {historyOpen && (history.length ? <div className="history-list">{history.map((record, index) => (
            <div className="history-row" key={`${record.time}-${index}`}>
              <button className="history-main" onClick={() => loadHistory(record)} title={t.historyLoad}>
                <span className="history-time">{formatTime(record.time)}</span>
                <span className="history-text">{record.text}</span>
              </button>
              <div className="history-row-actions">
                <button type="button" onClick={() => void deleteHistory(index)} aria-label={t.historyDelete}>{t.historyDelete}</button>
              </div>
            </div>
          ))}</div> : <div className="history-empty">{t.emptyHistory}</div>)}
        </section>
      </div>
      <div className="recognize-right">
        <article className={"recognize-panel result-panel" + (recognizing ? " is-running" : "")}><div className="result-heading"><h2>{t.ocr}</h2><div className="result-actions"><button type="button" onClick={() => void copyOcrText()} disabled={!ocrText || loading}>{copied ? t.copied : t.copy}</button><button type="button" onClick={clearOcrText} disabled={!ocrText || loading}>{t.clearText}</button></div></div><div className="ocr-controls"><button type="button" onClick={recognize} disabled={!image || loading}>{recognizing ? t.processing : t.ocr}</button><select value={source} onChange={(event) => setSource(event.target.value as OcrLanguage)}>{languages.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><button type="button" onClick={localRecognize} disabled={!image || loading || !localLanguages.languages.length}>{t.localOcr}</button>{localLanguages.languages.length > 0 ? <select aria-label={t.localOcrLanguage} value={localLanguage} onChange={(event) => setLocalLanguage(event.target.value)}>{localLanguages.languages.map((item) => <option key={item.tag} value={item.tag}>{item.name}</option>)}</select> : <span className="ocr-unavailable" role="note">{t.localOcrUnavailable}</span>}</div><textarea aria-label={t.ocr} value={ocrText} onChange={(event) => { setOcrText(event.target.value); setCopied(false); }} /></article>
        <article className={"recognize-panel result-panel" + (translating ? " is-running" : "")}><div className="result-heading"><h2>{t.translate}</h2><div className="result-actions"><button type="button" onClick={() => void copyTranslation()} disabled={!translation || loading}>{copiedTranslation ? t.copied : t.copy}</button><button type="button" onClick={() => setTranslation("")} disabled={!translation || loading}>{t.clearText}</button></div></div><div className="ocr-controls"><button type="button" onClick={translate} disabled={!ocrText || loading}>{translating ? t.processing : t.translate}</button><select value={target} onChange={(event) => setTarget(event.target.value as OcrLanguage)}>{languages.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div><textarea aria-label={t.translate} readOnly value={translation} /></article>
      </div>
    </div>
    {contextMenu && <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }} role="menu">
      <button role="menuitem" onClick={contextCopyImage}>{t.contextCopyImage}</button>
      <button role="menuitem" onClick={contextPasteImage}>{t.contextPasteImage}</button>
      <button role="menuitem" onClick={contextCopyText}>{t.contextCopyText}</button>
      <button role="menuitem" onClick={contextSave}>{t.contextSave}</button>
      <button role="menuitem" onClick={contextReset}>{t.contextReset}</button>
    </div>}
  </section>;
}
