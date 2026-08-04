import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Theme } from "../hooks/useTheme";
import "./SettingsPage.css";

type Lang = "zh" | "en";
type CloseBehavior = "tray" | "exit";
type ShortcutState = Record<string, string>;
interface AppConfig {
  theme: string; language: Lang; api_url: string; api_model: string; data_dir: string;
  close_behavior: CloseBehavior; clipboard_max_items: number; history_max_items: number;
  show_floating_widget: boolean; shortcuts: ShortcutState; has_api_key?: boolean;
}

const DEFAULT_SHORTCUTS: ShortcutState = { capture: "Alt+X", canvas_fit: "Ctrl+F", new_memo: "Ctrl+N", global_search: "Ctrl+Shift+F" };
const DEFAULT_CONFIG: AppConfig = { theme: "dark", language: "zh", api_url: "https://open.bigmodel.cn/api/paas/v4/chat/completions", api_model: "glm-4-flash", data_dir: "", close_behavior: "tray", clipboard_max_items: 50, history_max_items: 100, show_floating_widget: true, shortcuts: DEFAULT_SHORTCUTS };
const copy = {
  zh: { settings: "设置", theme: "主题", themeMode: "主题模式", dark: "暗色", light: "亮色", language: "语言", interfaceLanguage: "界面语言", chinese: "中文", english: "English", api: "API 配置", key: "API Key", keyPlaceholder: "输入 API Key", savedKey: "已保存的 API Key", url: "API URL", model: "模型", test: "测试连接", cancel: "取消", testing: "测试中...", clipboard: "剪贴板设置", history: "操作历史", maxItems: "最大条数", clipboardTip: "总条数上限；超出时自动删除最旧的非锁定项", historyTip: "超出时自动删除最旧记录", storage: "存储目录", browse: "浏览", storageTip: "留空则使用默认路径，切换后整个 .memopaws-rust 文件夹会移动", shortcuts: "快捷键", floating: "悬浮窗", show: "显示", hide: "隐藏", close: "关闭行为", closeWhen: "关闭窗口时", minimize: "最小化", save: "保存设置", saving: "保存中...", saved: "已保存", restart: "数据目录已迁移，请重启应用", conflict: "目标目录已存在数据，请选择处理方式", merge: "合并", overwrite: "覆盖", invalidShortcut: "快捷键无效", duplicateShortcut: "快捷键已被其他动作使用", connection: "连接成功", timeout: "网络超时", connect: "无法连接服务器", unauthorized: "API Key Invalid (401)", notFound: "路径错误 (404)", generic: "请求失败", vision: "多模态模型，支持图片识别", textOnly: "文本模型，不支持图片文字识别", cancelled: "已取消" },
  en: { settings: "Settings", theme: "Theme", themeMode: "Theme Mode", dark: "Dark", light: "Light", language: "Language", interfaceLanguage: "Language", chinese: "中文", english: "English", api: "API Configuration", key: "API Key", keyPlaceholder: "Enter API Key", savedKey: "Saved API Key", url: "API URL", model: "Model", test: "Test Connection", cancel: "Cancel", testing: "Testing...", clipboard: "Clipboard Settings", history: "History", maxItems: "Max Items", clipboardTip: "Max items; oldest unlocked items auto-deleted when exceeded", historyTip: "Oldest records auto-deleted when exceeded", storage: "Storage Directory", browse: "Browse", storageTip: "Leave empty for the default path; the entire .memopaws-rust folder will be moved", shortcuts: "Keyboard Shortcuts", floating: "Floating Widget", show: "Show", hide: "Hide", close: "Close Behavior", closeWhen: "When closing the window", minimize: "Minimize", save: "Save Settings", saving: "Saving...", saved: "Saved", restart: "Data directory migrated. Please restart the app.", conflict: "The target directory already contains data. Choose an action.", merge: "Merge", overwrite: "Overwrite", invalidShortcut: "Invalid shortcut", duplicateShortcut: "Shortcut is already used by another action", connection: "Connection successful", timeout: "Network timeout", connect: "Could not connect to server", unauthorized: "Invalid API Key (401)", notFound: "Path error (404)", generic: "Request failed", vision: "Multimodal model, image recognition supported", textOnly: "Text-only model, image recognition unavailable", cancelled: "Cancelled" },
} as const;
type Texts = (typeof copy)[Lang];
const shortcutLabels = { capture: ["截图识别", "Capture"], canvas_fit: ["画布自适应", "Canvas Fit"], new_memo: ["新建备忘录", "New Memo"], global_search: ["全局搜索", "Global Search"] };

interface Props { theme: Theme; onThemeChange: (theme: Theme) => void; onLanguageChange?: (lang: Lang) => void; }
export function SettingsPage({ theme, onThemeChange, onLanguageChange }: Props) {
  const [config, setConfig] = useState<AppConfig>({ ...DEFAULT_CONFIG, theme });
  const [lang, setLang] = useState<Lang>("zh");
  const [apiKey, setApiKey] = useState("");
  const [dataDir, setDataDir] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [apiState, setApiState] = useState<{ kind: string; detail?: string } | null>(null);
  const [apiRunning, setApiRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const cancelToken = useRef(0);
  const t = copy[lang];

  useEffect(() => { let active = true; Promise.all([invoke<Record<string, unknown>>("get_config"), invoke<string>("get_data_dir").catch(() => "")]).then(([raw, dir]) => { if (!active) return; const loaded = { ...DEFAULT_CONFIG, ...raw, shortcuts: { ...DEFAULT_SHORTCUTS, ...((raw.shortcuts as ShortcutState) || {}) } } as AppConfig; setConfig(loaded); setLang(loaded.language === "en" ? "en" : "zh"); setDataDir(dir || loaded.data_dir); }).catch((reason) => setError(errorText(reason))); return () => { active = false; }; }, []);
  const update = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => { setConfig((old) => ({ ...old, [key]: value })); setDirty(true); };
  const call = async <T,>(command: string, args?: Record<string, unknown>) => invoke<T>(command, args);
  const changeLanguage = (next: Lang) => { setLang(next); update("language", next); onLanguageChange?.(next); window.localStorage.setItem("language", next); void call("set_language", { language: next }).catch(() => {}); };
  const immediate = (key: "close_behavior" | "show_floating_widget", value: CloseBehavior | boolean) => { update(key, value as never); void call(key === "close_behavior" ? "set_close_behavior" : "set_floating_widget_visible", key === "close_behavior" ? { value } : { visible: value }).catch(() => {}); };
  const testConnection = async () => {
    if (apiRunning) { cancelToken.current++; setApiRunning(false); setApiState({ kind: "cancelled" }); void call("cancel_api_test").catch(() => {}); return; }
    if (!apiKey.trim() && !config.has_api_key) { setApiState({ kind: "missing" }); return; }
    const token = ++cancelToken.current; setApiRunning(true); setApiState({ kind: "testing" });
    try { const result = await call<Record<string, unknown>>("test_api_connection", { api_key: apiKey.trim() || undefined, api_url: config.api_url, api_model: config.api_model }); if (token !== cancelToken.current) return; setApiState(classifyApi(result)); } catch (reason) { if (token === cancelToken.current) setApiState(classifyApi({ error: errorText(reason) })); } finally { if (token === cancelToken.current) setApiRunning(false); }
  };
  const chooseDirectory = async () => { try { const selected = await call<string | null>("choose_data_dir"); if (selected) { setDataDir(selected); setDirty(true); setConflict(Boolean(await call("get_storage_dir_conflict", { path: selected }))); } } catch (reason) { setError(errorText(reason)); } };
  const save = async () => {
    setSaving(true); setError(""); setNotice(""); try { const previous = config.data_dir; const current = { ...config, data_dir: dataDir, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) }; await call("save_config", { config: current }); await call("set_clipboard_max_items", { value: current.clipboard_max_items }); await call("set_history_max_items", { value: current.history_max_items }); if (dataDir && dataDir !== previous) { const mode = conflict ? await chooseMigrationMode() : "merge"; if (!mode) return; const result = await call<{ restart_required?: boolean }>("migrate_data_dir", { data_dir: dataDir, path: dataDir, mode }); if (result?.restart_required) setNotice(t.restart); } setConfig(current); setApiKey(""); setDirty(false); if (!conflict) setNotice(t.saved); setConflict(false); } catch (reason) { setError(errorText(reason)); } finally { setSaving(false); }
  };
  const chooseMigrationMode = () => new Promise<"merge" | "overwrite" | null>((resolve) => { const answer = window.prompt(`${t.conflict} ${t.merge}/${t.overwrite}/${lang === "zh" ? "取消" : "Cancel"}`, t.merge); resolve(answer?.toLowerCase() === t.overwrite.toLowerCase() ? "overwrite" : answer?.toLowerCase() === t.merge.toLowerCase() ? "merge" : null); });
  const recordShortcut = (key: string, event: KeyboardEvent<HTMLInputElement>) => { event.preventDefault(); if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return; const parts = [event.ctrlKey && "Ctrl", event.altKey && "Alt", event.shiftKey && "Shift", event.metaKey && "Meta"].filter(Boolean) as string[]; const named = event.key === " " ? "Space" : event.key.length === 1 ? event.key.toUpperCase() : event.key; if (!parts.length || ["Unidentified", "Dead"].includes(named)) { setError(t.invalidShortcut); return; } const value = [...parts, named].join("+"); if (Object.entries(config.shortcuts).some(([name, current]) => name !== key && current === value)) { setError(t.duplicateShortcut); return; } update("shortcuts", { ...config.shortcuts, [key]: value }); setError(""); };
  const resetShortcut = (key: string) => update("shortcuts", { ...config.shortcuts, [key]: DEFAULT_SHORTCUTS[key] });
  const shortcutKeys = Object.keys(DEFAULT_SHORTCUTS);
  return <section className="settings-page">
     {(notice || error) && <div className={`settings-message ${error ? "is-error" : ""}`} role="alert">{error || notice}<button type="button" onClick={() => { setNotice(""); setError(""); }}>×</button></div>}
    <Group title={t.theme}><Row><Segmented value={theme} options={[["dark", t.dark], ["light", t.light]]} ariaLabel={t.themeMode} onChange={(v) => onThemeChange(v as Theme)} /></Row></Group>
    <Group title={t.language}><Row><Segmented value={lang} options={lang === "zh" ? [["en", t.english], ["zh", t.chinese]] : [["en", t.english], ["zh", t.chinese]]} onChange={(v) => changeLanguage(v as Lang)} /></Row></Group>
    <Group title={t.api}><Field label={t.key}><input aria-label={t.key} type="password" value={apiKey} placeholder={config.has_api_key ? t.savedKey : t.keyPlaceholder} onChange={(e) => { setApiKey(e.target.value); setDirty(true); }} autoComplete="off" /></Field><Field label={t.url}><input aria-label={t.url} value={config.api_url} onChange={(e) => update("api_url", e.target.value)} /></Field><Field label={t.model}><input aria-label={t.model} value={config.api_model} onChange={(e) => update("api_model", e.target.value)} /></Field><div className="settings-actions"><button type="button" onClick={testConnection}>{apiRunning ? t.cancel : t.test}</button><ApiStatus state={apiState} text={t} /></div></Group>
    <Group title={t.clipboard}><NumberField label={t.maxItems} ariaLabel={`${t.clipboard}${t.maxItems}`} value={config.clipboard_max_items} onChange={(v) => update("clipboard_max_items", v)} hint={t.clipboardTip} /></Group>
    <Group title={t.history}><NumberField label={t.maxItems} ariaLabel={`${t.history}${t.maxItems}`} value={config.history_max_items} onChange={(v) => update("history_max_items", v)} hint={t.historyTip} /></Group>
    <Group title={t.storage}><div className="settings-directory"><input aria-label={t.storage} value={dataDir} placeholder={t.storageTip} onChange={(e) => { setDataDir(e.target.value); setDirty(true); }} /><button type="button" onClick={chooseDirectory}>{t.browse}</button></div><p className="settings-hint">{t.storageTip}</p></Group>
    <Group title={t.shortcuts}>{shortcutKeys.map((key) => <div className="settings-shortcut" key={key}><span>{shortcutLabels[key as keyof typeof shortcutLabels][lang === "en" ? 1 : 0]}</span><input aria-label={`${shortcutLabels[key as keyof typeof shortcutLabels][lang === "en" ? 1 : 0]} shortcut`} value={config.shortcuts[key] || ""} readOnly onKeyDown={(e) => recordShortcut(key, e)} /><button type="button" onClick={() => resetShortcut(key)}>{lang === "en" ? "Reset" : "重置"}</button></div>)}</Group>
    <Group title={t.floating}><Row><Segmented value={config.show_floating_widget ? "show" : "hide"} options={[["show", t.show], ["hide", t.hide]]} onChange={(v) => immediate("show_floating_widget", v === "show")} /></Row></Group>
    <Group title={t.close}><Row><Segmented value={config.close_behavior} options={[["exit", t.close], ["tray", t.minimize]]} onChange={(v) => immediate("close_behavior", v as CloseBehavior)} /></Row></Group>
    <div className="settings-footer"><button className="settings-save" disabled={!dirty || saving} onClick={save}>{saving ? t.saving : t.save}</button></div>
  </section>;
}
function Group({ title, children }: { title: string; children: React.ReactNode }) { return <section className="settings-group"><h2>{title}</h2>{children}</section>; }
function Row({ children }: { children: React.ReactNode }) { return <div className="settings-row">{children}</div>; }
function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) { return <label className={`settings-field ${className}`.trim()}><span>{label}</span>{children}</label>; }
function NumberField({ label, ariaLabel, value, onChange, hint }: { label: string; ariaLabel: string; value: number; onChange: (value: number) => void; hint: string }) { return <Field label={label} className="is-inline"><input aria-label={ariaLabel} type="number" min={10} max={500} value={value} onChange={(e) => onChange(clamp(Number(e.target.value), 10, 500))} /><small>({hint})</small></Field>; }
function Segmented({ value, options, onChange, ariaLabel }: { value: string; options: [string, string][]; onChange: (value: string) => void; ariaLabel?: string }) { return <div className="settings-segmented" role="group" aria-label={ariaLabel}>{options.map(([key, label]) => <button type="button" key={key} aria-pressed={value === key} className={value === key ? "active" : ""} onClick={() => onChange(key)}>{label}</button>)}</div>; }
function ApiStatus({ state, text }: { state: { kind: string; detail?: string } | null; text: Texts }) { if (!state) return null; const labels: Record<string, string> = { testing: text.testing, missing: `${text.key} required`, cancelled: text.cancelled, timeout: text.timeout, connect: text.connect, unauthorized: text.unauthorized, notFound: text.notFound, generic: text.generic, success: text.connection, vision: text.vision, textOnly: text.textOnly }; return <span className={`settings-api-status ${state.kind === "success" || state.kind === "vision" ? "is-success" : state.kind === "testing" ? "is-pending" : "is-error"}`}>{labels[state.kind] || text.generic}{state.detail ? ` (${state.detail})` : ""}</span>; }
function classifyApi(result: Record<string, unknown>): { kind: string; detail?: string } { const elapsed = typeof result.elapsed_ms === "number" ? `${result.elapsed_ms} ms` : undefined; if (result.error === "timeout") return { kind: "timeout", detail: elapsed }; if (result.error === "connect") return { kind: "connect", detail: elapsed }; if (result.status_code === 200) { const vision = Boolean((result.vision_result as { success?: boolean } | undefined)?.success); return { kind: vision ? "vision" : "textOnly", detail: elapsed }; } if (result.status_code === 401) return { kind: "unauthorized" }; if (result.status_code === 404) return { kind: "notFound" }; return { kind: "generic", detail: typeof result.status_code === "number" ? `HTTP ${result.status_code}` : undefined }; }
function clamp(value: number, min: number, max: number) { return Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : min; }
function errorText(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
