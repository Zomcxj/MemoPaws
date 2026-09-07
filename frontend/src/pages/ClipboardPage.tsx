import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { SegmentedControl } from "../components/SegmentedControl";
import type { Lang } from "../i18n/lang";
import "./ClipboardPage.css";

interface ClipboardItem {
  id: number;
  time: string;
  content_type: string;
  text: string | null;
  image_path: string | null;
  locked: boolean;
}

const errorText = (reason: unknown) => (reason instanceof Error ? reason.message : String(reason));

// 兼容三种历史格式：毫秒时间戳（新）、秒时间戳（旧）、格式化字符串（更早的遗留数据）
const formatClipboardTime = (time: string) => {
  const value = Number(time);
  if (Number.isNaN(value)) return time;
  return new Date(value > 1e12 ? value : value * 1000).toLocaleString();
};

const MIN_ZOOM = 0.1;
const MAX_ZOOM = 8;
const ZOOM_STEP = 1.25;
const PAN_STEP = 40;

interface PreviewView {
  zoom: number;
  x: number;
  y: number;
}

const IDLE_VIEW: PreviewView = { zoom: 1, x: 0, y: 0 };

const clampZoom = (value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));

const copy = {
  zh: {
    search: "搜索剪贴板内容…",
    searchShort: "搜索...",
    list: "列表",
    grid: "组件",
    noMatch: "未找到匹配记录",
    empty: "暂无剪贴板记录",
    loadImage: "加载图片",
    recognize: "发送到识别",
    copy: "复制",
    edit: "编辑",
    save: "保存",
    selectAll: "全选",
    clearSelection: "取消全选",
    deleteSelected: "删除所选",
    lock: "锁定",
    unlock: "解锁",
    locked: "已锁定",
    delete: "删除",
    close: "关闭",
    tip: "双击复制 · 右键菜单（多选/锁定/删除）",
    imageAlt: "剪贴板图片",
    imageTag: "[图片]",
    preview: "预览图片",
    previewTitle: "图片预览",
    zoomIn: "放大",
    zoomOut: "缩小",
    resetZoom: "重置",
    zoomLevel: "当前缩放",
    previewHint: "滚轮缩放 · 拖拽平移 · 双击复位 · Esc 关闭",
  },
  en: {
    search: "Search clipboard content...",
    searchShort: "Search...",
    list: "List",
    grid: "Grid",
    noMatch: "No matching records",
    empty: "No clipboard records",
    loadImage: "Load image",
    recognize: "Send to recognition",
    copy: "Copy",
    edit: "Edit",
    save: "Save",
    selectAll: "Select all",
    clearSelection: "Clear selection",
    deleteSelected: "Delete selected",
    lock: "Lock",
    unlock: "Unlock",
    locked: "Locked",
    delete: "Delete",
    close: "Close",
    tip: "Double-click to copy · Right-click menu (multi-select/lock/delete)",
    imageAlt: "Clipboard image",
    imageTag: "[Image]",
    preview: "Preview image",
    previewTitle: "Image preview",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    resetZoom: "Reset",
    zoomLevel: "Current zoom",
    previewHint: "Wheel to zoom · Drag to pan · Double-click to reset · Esc to close",
  },
} as const;

interface Props {
  language?: Lang;
}

export function ClipboardPage({ language = "zh" }: Props) {
  const [items, setItems] = useState<ClipboardItem[]>([]);
  const [error, setError] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"list" | "grid">("list");
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [imageBytes, setImageBytes] = useState<Record<number, number[]>>({});
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [previewView, setPreviewView] = useState<PreviewView>(IDLE_VIEW);
  const [dragging, setDragging] = useState(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const t = copy[language];

  const run = async (operation: () => Promise<void>) => {
    setError("");
    try { await operation(); } catch (reason) { setError(errorText(reason)); }
  };

  // 按倍率缩放，锚点为相对 stage 中心的偏移（默认 stage 中心）。
  // 锚点在缩放前后保持贴合同一图像位置，因此缩放平滑不跳变。
  const zoomBy = useCallback((factor: number, anchorX = 0, anchorY = 0) => {
    setPreviewView((current) => {
      const zoom = clampZoom(current.zoom * factor);
      if (zoom === current.zoom) return current;
      const ratio = zoom / current.zoom;
      return {
        zoom,
        x: anchorX - (anchorX - current.x) * ratio,
        y: anchorY - (anchorY - current.y) * ratio,
      };
    });
  }, []);

  const resetView = useCallback(() => setPreviewView(IDLE_VIEW), []);

  const closePreview = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    setPreviewId(null);
  }, []);

  const openPreview = async (id: number) => {
    if (!(await loadImage(id))) return;
    setPreviewView(IDLE_VIEW);
    setPreviewId(id);
  };

  // 切换记录或关闭预览时重置缩放与位移
  useEffect(() => {
    setPreviewView(IDLE_VIEW);
    dragRef.current = null;
    setDragging(false);
  }, [previewId]);

  // 预览的记录被删除 / 过滤掉时自动关闭
  useEffect(() => {
    if (previewId !== null && !items.some((item) => item.id === previewId)) closePreview();
  }, [items, previewId, closePreview]);

  // 滚轮缩放：需要 passive:false 才能 preventDefault 阻止页面滚动
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || previewId === null) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = stage.getBoundingClientRect();
      const anchorX = event.clientX - rect.left - rect.width / 2;
      const anchorY = event.clientY - rect.top - rect.height / 2;
      // 指数映射：不同设备的 deltaY 幅度差异不会造成跳变
      zoomBy(Math.exp(-event.deltaY * 0.0015), anchorX, anchorY);
    };
    stage.addEventListener("wheel", onWheel, { passive: false });
    return () => stage.removeEventListener("wheel", onWheel);
  }, [previewId, zoomBy]);

  // 键盘可用性：Esc 关闭、+/- 缩放、0 复位、方向键平移
  useEffect(() => {
    if (previewId === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePreview();
        return;
      }
      // 焦点仍在输入框时不劫持字符/方向键
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      switch (event.key) {
        case "+":
        case "=":
          event.preventDefault();
          zoomBy(ZOOM_STEP);
          break;
        case "-":
        case "_":
          event.preventDefault();
          zoomBy(1 / ZOOM_STEP);
          break;
        case "0":
          event.preventDefault();
          resetView();
          break;
        case "ArrowLeft":
        case "ArrowRight":
        case "ArrowUp":
        case "ArrowDown": {
          event.preventDefault();
          const dx = event.key === "ArrowLeft" ? -PAN_STEP : event.key === "ArrowRight" ? PAN_STEP : 0;
          const dy = event.key === "ArrowUp" ? -PAN_STEP : event.key === "ArrowDown" ? PAN_STEP : 0;
          setPreviewView((current) => ({ ...current, x: current.x + dx, y: current.y + dy }));
          break;
        }
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewId, closePreview, zoomBy, resetView]);

  const onStagePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: previewView.x,
      originY: previewView.y,
    };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onStagePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setPreviewView((current) => ({
      ...current,
      x: drag.originX + (event.clientX - drag.startX),
      y: drag.originY + (event.clientY - drag.startY),
    }));
  };

  const onStagePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const refresh = async () => {
    const list = await invoke<ClipboardItem[]>("clipboard_list");
    setItems(list.map((item) => ({ ...item, locked: Boolean(item.locked) })));
  };

  useEffect(() => {
    let active = true;
    invoke<ClipboardItem[]>("clipboard_list")
      .then((list) => {
        if (active) setItems(list.map((item) => ({ ...item, locked: Boolean(item.locked) })));
      })
      .catch((reason) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const unlisten = listen("clipboard-changed", () => {
      refresh().catch((reason) => setError(errorText(reason)));
    });
    return () => {
      unlisten.then((stop) => stop());
    };
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

  // 仅在卸载时释放 object URL：依赖 imageUrls 会在新增图片时提前吊销已有 URL
  const imageUrlsRef = useRef<Record<number, string>>({});
  imageUrlsRef.current = imageUrls;
  useEffect(() => {
    return () => {
      Object.values(imageUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  const loadImage = async (id: number) => {
    if (imageUrls[id]) return true;
    try {
      const bytes = await invoke<number[]>("clipboard_get_image", { id });
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      setImageBytes((prev) => ({ ...prev, [id]: bytes }));
      setImageUrls((prev) => ({ ...prev, [id]: URL.createObjectURL(blob) }));
      return true;
    } catch (reason) {
      setError(errorText(reason));
      return false;
    }
  };

  useEffect(() => {
    if (view !== "grid") return;
    for (const item of items) {
      if (item.content_type === "image" && !imageUrls[item.id]) {
        void loadImage(item.id);
      }
    }
  }, [items, view]);

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const copyImage = async (id: number) => {
    try {
      const bytes = imageBytes[id] ?? await invoke<number[]>("clipboard_get_image", { id });
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const removeItem = async (id: number) => {
    await removeItems([id]);
  };

  const removeItems = async (ids: number[]) => {
    if (ids.length === 0) return;
    setError("");
    try {
      await invoke("clipboard_delete_many", { ids });
      setSelectedIds([]);
      await refresh();
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const toggleLocked = async (item: ClipboardItem) => {
    setError("");
    try {
      await invoke("clipboard_set_locked", { id: item.id, locked: !item.locked });
      await refresh();
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const updateText = async (id: number) => {
    setError("");
    try {
      await invoke("clipboard_update_text", { id, text: editText });
      setEditingId(null);
      await refresh();
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const toggleSelected = (id: number) => {
    if (items.find((item) => item.id === id)?.locked) return;
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  };

  const filtered = search
    ? items.filter((item) => item.text?.toLowerCase().includes(search.toLowerCase()))
    : items;

  const selectable = filtered.filter((item) => !item.locked);
  const allFilteredSelected = selectable.length > 0 && selectable.every((item) => selectedIds.includes(item.id));

  return (
    <section className="clipboard-page">
      <div className="clipboard-shell">
        <div className="clipboard-toolbar">
          <div className="clipboard-search">
            <input
              aria-label={t.search}
              placeholder={t.searchShort}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <SegmentedControl
            className="clipboard-view-toggle"
            value={view}
            options={[
              ["list", t.list],
              ["grid", t.grid],
            ]}
            onChange={(next) => changeView(next as "list" | "grid")}
          />
          <button type="button" onClick={() => setSelectedIds(allFilteredSelected ? [] : selectable.map((item) => item.id))}>
            {allFilteredSelected ? t.clearSelection : t.selectAll}
          </button>
          <button type="button" className="clipboard-bulk-delete" disabled={selectedIds.length === 0} onClick={() => removeItems(selectedIds)}>
            {t.deleteSelected} ({selectedIds.length})
          </button>
          <button type="button" onClick={() => void run(async () => { await invoke("clipboard_paste_image"); setItems(await invoke<ClipboardItem[]>("clipboard_list")); })}>
            {language === "zh" ? "粘贴图片" : "Paste Image"}
          </button>
        </div>
        {error && (
          <div className="clipboard-error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError("")} title={t.close} aria-label={t.close}>
              <img src="/assets/icons/close.svg" alt="" aria-hidden="true" />
              {t.close}
            </button>
          </div>
        )}
        <div className="clipboard-body">
          {filtered.length === 0 ? (
            <div className="clipboard-empty">{search ? t.noMatch : t.empty}</div>
          ) : (
            <div className={`clipboard-items ${view}`}>
              {filtered.map((item) => (
                <article key={item.id} className="clipboard-item">
                  <label className="clipboard-select">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(item.id)}
                      onChange={() => toggleSelected(item.id)}
                      aria-label={`${item.locked ? t.locked : ""} ${item.id}`}
                      disabled={item.locked}
                    />
                    {item.locked && <span className="clipboard-locked">{t.locked}</span>}
                    <small className="clipboard-time">{formatClipboardTime(item.time)}</small>
                  </label>
                  <div className="clipboard-item-body">
                    {view === "list" ? (
                      <div
                        className="clipboard-list-summary"
                        title={formatClipboardLine(item)}
                        onDoubleClick={() => item.content_type !== "image" && item.text && copyText(item.text)}
                      >
                        {formatClipboardLine(item)}
                      </div>
                    ) : item.content_type === "image" ? (
                      <div className="clipboard-image-wrap">
                        {imageUrls[item.id] ? (
                          <button
                            type="button"
                            className="clipboard-image-open"
                            onClick={() => void openPreview(item.id)}
                            title={t.preview}
                            aria-label={t.preview}
                          >
                            <img src={imageUrls[item.id]} alt={t.imageAlt} />
                          </button>
                        ) : (
                          <button className="clipboard-image-load" onClick={() => loadImage(item.id)} title={t.loadImage}>
                            <img src="/assets/icons/download.svg" alt="" aria-hidden="true" />
                            {t.loadImage}
                          </button>
                        )}
                        <div className="clipboard-image-name" title={item.image_path || undefined}>
                          {item.image_path?.split(/[\\/]/).pop() || "image.png"}
                        </div>
                      </div>
                    ) : (
                      <div className="clipboard-text-wrap">
                        <pre onDoubleClick={() => item.text && copyText(item.text)} title={item.text ? t.copy : undefined}>
                            {formatClipboardLine(item)}
                        </pre>
                      </div>
                    )}
                  </div>
                  <div className="clipboard-item-actions">
                    {item.content_type === "image" ? (
                      <button
                        type="button"
                        className="clipboard-action clipboard-icon-action clipboard-preview-action"
                        onClick={() => void openPreview(item.id)}
                        title={t.preview}
                        aria-label={t.preview}
                      ><img src="/assets/icons/expand.svg" alt="" aria-hidden="true" /></button>
                    ) : (
                      <button
                        type="button"
                        className="clipboard-action clipboard-icon-action clipboard-edit"
                        onClick={() => { setEditingId(item.id); setEditText(item.text || ""); }}
                        title={t.edit}
                        aria-label={t.edit}
                      ><img src="/assets/icons/edit.svg" alt="" aria-hidden="true" /></button>
                    )}
                    <button
                      type="button"
                      className="clipboard-action clipboard-icon-action clipboard-copy"
                      onClick={() => item.content_type === "image" ? void copyImage(item.id) : item.text && copyText(item.text)}
                      title={t.copy}
                      aria-label={t.copy}
                    ><img src="/assets/icons/clipboard.svg" alt="" aria-hidden="true" /></button>
                    <button
                      type="button"
                      className="clipboard-action clipboard-icon-action clipboard-lock"
                      onClick={() => toggleLocked(item)}
                      title={item.locked ? t.unlock : t.lock}
                      aria-label={item.locked ? t.unlock : t.lock}
                    ><img src="/assets/icons/lock.svg" alt="" aria-hidden="true" /></button>
                    <button
                      type="button"
                      className="clipboard-action clipboard-icon-action clipboard-delete"
                      onClick={() => removeItem(item.id)}
                      title={t.delete}
                      aria-label={t.delete}
                    ><img src="/assets/icons/close.svg" alt="" aria-hidden="true" /></button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
      <p className="clipboard-tip">{t.tip}</p>
      {editingId !== null && (
        <div className="clipboard-edit-modal" role="presentation" onMouseDown={() => setEditingId(null)}>
          <div className="clipboard-edit-dialog" role="dialog" aria-modal="true" aria-label={t.edit} onMouseDown={(event) => event.stopPropagation()}>
            <div className="clipboard-edit-dialog-head"><h2>{t.edit}</h2></div>
            <textarea
              autoFocus
              value={editText}
              onChange={(event) => setEditText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setEditingId(null);
                if (event.key === "Enter" && event.ctrlKey) void updateText(editingId);
              }}
            />
            <div className="clipboard-edit-dialog-actions">
              <button type="button" onClick={() => setEditingId(null)}>{t.close}</button>
              <button type="button" className="primary" onClick={() => void updateText(editingId)}>{t.save}</button>
            </div>
          </div>
        </div>
      )}
      {previewId !== null && imageUrls[previewId] && (
        <div
          className="clipboard-preview"
          role="dialog"
          aria-modal="true"
          aria-label={t.previewTitle}
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) closePreview();
          }}
        >
          <div className="clipboard-preview-bar">
            <span className="clipboard-preview-zoom" aria-live="polite">
              {t.zoomLevel} {Math.round(previewView.zoom * 100)}%
            </span>
            <button type="button" onClick={() => zoomBy(1 / ZOOM_STEP)} title={t.zoomOut} aria-label={t.zoomOut}>-</button>
            <button type="button" onClick={() => zoomBy(ZOOM_STEP)} title={t.zoomIn} aria-label={t.zoomIn}>+</button>
            <button type="button" onClick={resetView} title={t.resetZoom} aria-label={t.resetZoom}>{t.resetZoom}</button>
            <button type="button" className="clipboard-preview-close" onClick={closePreview} title={t.close} aria-label={t.close}>
              <img src="/assets/icons/close.svg" alt="" aria-hidden="true" />
              {t.close}
            </button>
          </div>
          <div
            ref={stageRef}
            className={`clipboard-preview-stage${dragging ? " dragging" : ""}`}
            onPointerDown={onStagePointerDown}
            onPointerMove={onStagePointerMove}
            onPointerUp={onStagePointerUp}
            onPointerCancel={onStagePointerUp}
            onDoubleClick={resetView}
          >
            <img
              src={imageUrls[previewId]}
              alt={t.imageAlt}
              draggable={false}
              style={{ transform: `translate3d(${previewView.x}px, ${previewView.y}px, 0) scale(${previewView.zoom})` }}
            />
          </div>
          <p className="clipboard-preview-hint">{t.previewHint}</p>
        </div>
      )}
    </section>
  );
}

function formatClipboardLine(item: ClipboardItem) {
  if (item.content_type === "image") {
    return item.image_path?.split(/[\\/]/).pop() || "image.png";
  }
  return (item.text || "").split(/\r?\n/, 1)[0];
}
