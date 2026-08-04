import { ChangeEvent, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import "./RecognizePage.css";

type Language = "zh" | "en" | "ja" | "ko" | "fr" | "de" | "es" | "ru";
interface KeyEntry { id: number; name: string; type: string; url: string }
interface HistoryRecord { time: string; type: string; text: string; ocr_text?: string; translate_text?: string }
interface TextResult { text: string }

const languages: { value: Language; label: string }[] = [
  { value: "zh", label: "中文" }, { value: "en", label: "English" },
  { value: "ja", label: "日本語" }, { value: "ko", label: "한국어" },
  { value: "fr", label: "Français" }, { value: "de", label: "Deutsch" },
  { value: "es", label: "Español" }, { value: "ru", label: "Русский" },
];
const MAX_IMAGE_BYTES = 25 * 1024 * 1024;
const errorText = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

export function RecognizePage() {
  const [keyId, setKeyId] = useState<number | "">("");
  const [model] = useState("glm-4v-flash");
  const [source, setSource] = useState<Language | "">("zh");
  const [target, setTarget] = useState<Language>("en");
  const [image, setImage] = useState<Uint8Array | null>(null);
  const [preview, setPreview] = useState("");
  const [ocrText, setOcrText] = useState("");
  const [translation, setTranslation] = useState("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [rectWidth, setRectWidth] = useState(3);
  const requestToken = useRef(0);

  const refreshHistory = async () => setHistory(await invoke<HistoryRecord[]>("history_list"));

  useEffect(() => {
    let active = true;
    Promise.all([invoke<KeyEntry[]>("key_list"), invoke<HistoryRecord[]>("history_list")])
      .then(([entries, records]) => {
        if (!active) return;
        const llm = entries.filter((entry) => entry.type === "llm");
        setKeyId(llm[0]?.id ?? ""); setHistory(records);
      }).catch((reason) => { if (active) setError(errorText(reason)); });
    return () => { active = false; requestToken.current += 1; };
  }, []);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const importImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) { setError("请选择图片文件"); return; }
    if (file.size > MAX_IMAGE_BYTES) { setError("图片不能超过 25 MiB"); return; }
    requestToken.current += 1;
    setError(""); setOcrText(""); setTranslation("");
    setImage(new Uint8Array(await file.arrayBuffer()));
    setPreview(URL.createObjectURL(file));
  };

  const requireConfig = () => {
    if (keyId === "") throw new Error("请先在密钥管理中添加并选择 LLM 密钥");
    if (!model.trim()) throw new Error("请输入模型名称");
    return { keyEntryId: keyId, model: model.trim() };
  };

  const recognize = async (token = ++requestToken.current) => {
    if (!image) throw new Error("请先导入图片");
    const result = await invoke<TextResult>("ai_ocr", { image: Array.from(image), ...requireConfig() });
    if (token !== requestToken.current) return "";
    setOcrText(result.text); setTranslation("");
    return result.text;
  };

  const translate = async (text = ocrText, token = ++requestToken.current) => {
    if (!text.trim()) throw new Error("没有可翻译的识别文本");
    const result = await invoke<TextResult>("ai_translate", { text, target, source: source || null, ...requireConfig() });
    if (token !== requestToken.current) return;
    setTranslation(result.text);
  };

  const run = async (operation: (token: number) => Promise<unknown>) => {
    const token = ++requestToken.current;
    setLoading(true); setError("");
    try { await operation(token); if (token === requestToken.current) await refreshHistory(); }
    catch (reason) { if (token === requestToken.current) setError(errorText(reason)); }
    finally { if (token === requestToken.current) setLoading(false); }
  };

  const runAll = () => void run(async (token) => {
    const text = await recognize(token);
    if (text && token === requestToken.current) await translate(text, token);
  });

  const removeHistory = (index: number) => void run(async () => { await invoke("history_delete", { index }); });
  const clearHistory = () => {
    if (history.length && window.confirm("清空全部识别与翻译历史？")) void run(async () => { await invoke("history_clear"); });
  };
  const restore = (record: HistoryRecord) => {
    requestToken.current += 1;
    setOcrText(record.ocr_text ?? (record.type === "ocr" ? record.text : ""));
    setTranslation(record.translate_text ?? (record.type === "translate" ? record.text : ""));
    setError("");
  };

  const startCapture = async () => {
    try {
      const result = await invoke<{ image: number[]; preview: string }>("capture_screen");
      setImage(new Uint8Array(result.image));
      setPreview(result.preview);
      setOcrText(""); setTranslation(""); setError("");
    } catch (reason) { setError(errorText(reason)); }
  };

  const preprocess = async (mode: "gray" | "binary") => {
    if (!image) return;
    try {
      const result = await invoke<{ image: number[] }>("image_preprocess", { image: Array.from(image), mode });
      const blob = new Blob([new Uint8Array(result.image)], { type: "image/png" });
      setImage(new Uint8Array(result.image));
      if (preview) URL.revokeObjectURL(preview);
      setPreview(URL.createObjectURL(blob));
    } catch (reason) { setError(errorText(reason)); }
  };

  const resetImage = () => {
    if (preview) { URL.revokeObjectURL(preview); setPreview(""); }
    setImage(null); setOcrText(""); setTranslation(""); setError("");
  };

  const clearImage = () => {
    if (preview) URL.revokeObjectURL(preview);
    setImage(null); setPreview(""); setOcrText(""); setTranslation(""); setError("");
  };

  const exportImage = () => {
    if (!image) return;
    const blob = new Blob([new Uint8Array(image)], { type: "image/png" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `memopaws-${Date.now()}.png`; anchor.click();
    URL.revokeObjectURL(url);
  };

  const recognizeLocal = async (token: number) => {
    if (!image) throw new Error("请先导入图片");
    const result = await invoke<TextResult>("local_ocr", { image: Array.from(image) });
    if (token !== requestToken.current) return "";
    setOcrText(result.text); setTranslation("");
    return result.text;
  };

  const translateOnline = async (token: number) => {
    if (!ocrText.trim()) throw new Error("没有可翻译的识别文本");
    const result = await invoke<TextResult>("online_translate", { text: ocrText, target, source: source || null });
    if (token !== requestToken.current) return;
    setTranslation(result.text);
  };

  const icon = (name: string) => `/assets/icons/${name}.svg`;

  return <section className="recognize-page">
    <header className="recognize-toolbar">
      <div className="toolbar-actions">
        <label className="tool-button" title="导入图片"><img src={icon("import")} alt="" />导入<input type="file" accept="image/*" onChange={(event) => void importImage(event)} /></label>
        <button className="tool-button" onClick={startCapture}><img src={icon("capture")} alt="" />截图</button>
        <button className="tool-button" onClick={() => {}}><img src={icon("crop")} alt="" />裁剪</button>
        <button className="tool-button" onClick={() => {}}><img src={icon("rect")} alt="" />矩形</button>
        <span className="toolbar-divider" />
        <label className="toolbar-field">线宽<input type="range" min={1} max={12} value={rectWidth} onChange={(e) => setRectWidth(Number(e.target.value))} /><span>{rectWidth}</span></label>
        <span className="toolbar-divider" />
        <button className="tool-button" onClick={() => void run((token) => preprocess("gray").then(() => token))}><img src={icon("grayscale")} alt="" />灰度</button>
        <button className="tool-button" onClick={() => void run((token) => preprocess("binary").then(() => token))}><img src={icon("binary")} alt="" />二值化</button>
        <button className="tool-button" onClick={resetImage}><img src={icon("reset")} alt="" />重置</button>
        <button className="tool-button" onClick={clearImage}><img src={icon("clear")} alt="" />清空</button>
        <button className="tool-button" onClick={exportImage}><img src={icon("save")} alt="" />保存图片</button>
      </div>
      <button className="recognize-primary" disabled={loading || !image} onClick={runAll}>{loading ? "处理中..." : "One Punch"}</button>
    </header>
    {error && <div className="recognize-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}
    <div className="recognize-workspace">
      <div className="recognize-left">
        <article className="recognize-panel image-panel">{preview ? <div className="image-canvas"><img src={preview} alt="待识别图片预览" /></div> : <label className="image-empty"><img src={icon("import")} alt="" /><strong>导入图片开始识别</strong><small>支持常见图片格式，最大 25 MiB</small><input type="file" accept="image/*" onChange={(event) => void importImage(event)} /></label>}</article>
        <section className="recognize-history"><div className="history-head"><h2>操作历史</h2><button disabled={!history.length || loading} onClick={clearHistory}><img src={icon("clear")} alt="" />清空</button></div>{history.length === 0 ? <div className="history-empty">暂无成功记录</div> : <div className="history-list">{history.map((record, index) => <article key={`${record.time}-${index}`}><button className="history-main" onClick={() => restore(record)} onContextMenu={(e) => { e.preventDefault(); removeHistory(index); }}><strong>[{record.time}] {record.type === "translate" ? "翻译" : "系统"} {record.text || ""}</strong></button></article>)}</div>}<p className="history-tip">点击恢复 | 右键删除</p></section>
      </div>
      <div className="recognize-right">
        <article className="recognize-panel result-panel">
          <div className="panel-heading"><h2>识别结果</h2></div>
          <div className="ocr-buttons">
            <button onClick={() => void run((token) => recognizeLocal(token))}>本地识别</button>
            <button onClick={() => void run((token) => recognize(token))}>AI识别</button>
            <select value={source} onChange={(e) => setSource(e.target.value as Language)}>{languages.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
          </div>
          <textarea value={ocrText} placeholder="" onChange={(event) => { requestToken.current += 1; setOcrText(event.target.value); setTranslation(""); }} />
        </article>
        <article className="recognize-panel result-panel">
          <div className="panel-heading"><h2>翻译结果</h2></div>
          <div className="ocr-buttons">
            <button onClick={() => void run((token) => translateOnline(token))}>在线翻译</button>
            <button onClick={() => void run((token) => translate(ocrText, token))}>AI翻译</button>
            <select value={target} onChange={(e) => setTarget(e.target.value as Language)}>{languages.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
          </div>
          <textarea readOnly value={translation} />
        </article>
      </div>
    </div>
  </section>;
}
