import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import "./ClipboardPage.css";

interface ClipboardItem {
  id: number;
  time: string;
  content_type: string;
  text: string | null;
  image_path: string | null;
}

const errorText = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

type Language = "zh" | "en";
const language = (): Language => {
  const value = ["language", "app_language", "interface_language"]
    .map((key) => window.localStorage.getItem(key))
    .find((value) => value === "en" || value === "zh");
  return value === "en" ? "en" : "zh";
};

export function ClipboardPage() {
  const [items, setItems] = useState<ClipboardItem[]>([]);
  const [error, setError] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"list" | "grid">("list");
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const lang = language();
  const text = lang === "en" ? {
    title: "Clipboard", records: "records", list: "List", grid: "Grid",
    search: "Search clipboard content...", noMatch: "No matching records", empty: "No clipboard records",
    loadImage: "Load image", copy: "Copy", delete: "Delete", close: "Close", tip: "Double-click to copy · Right-click menu (multi-select/lock/delete)"
  } : {
    title: "剪贴板", records: "条记录", list: "列表", grid: "组件",
    search: "搜索剪贴板内容…", noMatch: "未找到匹配记录", empty: "暂无剪贴板记录",
    loadImage: "加载图片", copy: "复制", delete: "删除", close: "关闭", tip: "双击复制 · 右键菜单（多选/锁定/删除）"
  };

  const refresh = async () => {
    setItems(await invoke<ClipboardItem[]>("clipboard_list"));
  };

  useEffect(() => {
    let active = true;
    invoke<ClipboardItem[]>("clipboard_list")
      .then((list) => { if (active) setItems(list); })
      .catch((reason) => { if (active) setError(errorText(reason)); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const saved = window.localStorage.getItem("clipboard_view_mode");
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);

  const changeView = (next: "list" | "grid") => {
    setView(next);
    window.localStorage.setItem("clipboard_view_mode", next);
  };

  useEffect(() => {
    return () => { Object.values(imageUrls).forEach((url) => URL.revokeObjectURL(url)); };
  }, [imageUrls]);

  const loadImage = async (id: number) => {
    if (imageUrls[id]) return;
    try {
      const bytes = await invoke<number[]>("clipboard_get_image", { id });
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      setImageUrls((prev) => ({ ...prev, [id]: URL.createObjectURL(blob) }));
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const copyText = async (text: string) => {
    try { await navigator.clipboard.writeText(text); }
    catch (reason) { setError(errorText(reason)); }
  };

  const removeItem = async (id: number) => {
    setError("");
    try { await invoke("clipboard_delete", { id }); await refresh(); }
    catch (reason) { setError(errorText(reason)); }
  };

  const filtered = search
    ? items.filter((item) => item.text?.toLowerCase().includes(search.toLowerCase()))
    : items;

  return <section className="clipboard-page">
    <div className="clipboard-shell">
      <div className="clipboard-toolbar">
        <div className="clipboard-search">
          <input aria-label={text.search} placeholder={lang === "en" ? "Search..." : "搜索..."} value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
        </div>
        <div className="clipboard-view-toggle">
          <button className={view === "list" ? "active" : ""} onClick={() => changeView("list")}>{text.list}</button>
          <button className={view === "grid" ? "active" : ""} onClick={() => changeView("grid")}>{text.grid}</button>
        </div>
      </div>
      {error && <div className="clipboard-error" role="alert"><span>{error}</span><button onClick={() => setError("")} title={text.close} aria-label={text.close}><img src="/assets/icons/close.svg" alt="" aria-hidden="true" />{text.close}</button></div>}
      <div className="clipboard-body">
        {filtered.length === 0
          ? <div className="clipboard-empty">{search ? text.noMatch : text.empty}</div>
          : <div className={`clipboard-items ${view}`}>
              {filtered.map((item) => (
                <article key={item.id} className="clipboard-item">
                  {item.content_type === "image"
                    ? <div className="clipboard-image-wrap">
                        {imageUrls[item.id]
                          ? <img src={imageUrls[item.id]} alt="剪贴板图片" onClick={() => loadImage(item.id)} />
                          : <button className="clipboard-image-load" onClick={() => loadImage(item.id)} title={text.loadImage}><img src="/assets/icons/download.svg" alt="" aria-hidden="true" />{text.loadImage}</button>}
                      </div>
                    : <div className="clipboard-text-wrap">
                        <pre onDoubleClick={() => item.text && copyText(item.text)} title={item.text ? text.copy : undefined}>{item.content_type === "image" ? "" : formatClipboardLine(item)}</pre>
                        <button className="clipboard-copy" onClick={() => item.text && copyText(item.text)} title={text.copy} aria-label={text.copy}><img src="/assets/icons/clipboard.svg" alt="" aria-hidden="true" />{text.copy}</button>
                      </div>}
                  <div className="clipboard-item-footer">
                    <small>{view === "grid" ? new Date(Number(item.time) * 1000).toLocaleString() : ""}</small>
                    <button className="clipboard-delete" onClick={() => removeItem(item.id)} title={text.delete} aria-label={text.delete}><img src="/assets/icons/close.svg" alt="" aria-hidden="true" />{text.delete}</button>
                  </div>
                </article>
              ))}
            </div>}
      </div>
    </div>
    <p className="clipboard-tip">{text.tip}</p>
  </section>;
}

function formatClipboardLine(item: ClipboardItem) {
  const stamp = new Date(Number(item.time) * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const time = `${stamp.getFullYear()}-${pad(stamp.getMonth() + 1)}-${pad(stamp.getDate())} ${pad(stamp.getHours())}:${pad(stamp.getMinutes())}:${pad(stamp.getSeconds())}`;
  if (item.content_type === "image") {
    const name = item.image_path?.split(/[\\/]/).pop() || "image.png";
    return `${time}  [图片] ${name}`;
  }
  return `${time}  ${item.text || ""}`;
}
