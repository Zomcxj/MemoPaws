import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { SegmentedControl } from "../components/SegmentedControl";
import type { Lang } from "../i18n/lang";
import "./MemoPage.css";

interface Memo {
  id: number;
  time: string;
  created: string;
  modified: string;
  title: string;
  content: string;
  tags: string[];
  _file?: string;
}

interface SearchResult {
  memo: Memo;
  line_number: number;
}

type ViewMode = "edit" | "split" | "preview";

const copy = {
  zh: {
    page: "备忘录",
    new: "+ 新建",
    import: "导入",
    export: "导出",
    delete: "删除",
    search: "搜索备忘录...",
    loading: "正在整理备忘录…",
    searching: "正在搜索备忘录…",
    searchFail: "搜索失败：",
    noMatch: "没有匹配的备忘录",
    empty: "还没有备忘录，点击 + 开始记录",
    untitled: "未命名备忘录",
    counting: "搜索中…",
    count: (n: number) => `${n} 条`,
    close: "关闭",
    blankTitle: "选择一条备忘录",
    blankHint: "或创建一条新的记录。",
    title: "标题",
    tags: "标签:",
    tagsPh: "逗号分隔，如：工作,重要",
    content: "Markdown 内容",
    contentPh: "用 Markdown 写下此刻…",
    previewing: "正在生成预览…",
    save: "保存",
    saving: "保存中…",
    edit: "编辑",
    sync: "同步",
    preview: "预览",
    mode: "视图模式",
    newTitle: "新备忘录",
    imported: "导入的备忘录",
    importFail: "导入失败：",
    defaultFile: "备忘录",
    unsaved: "当前备忘录有未保存修改，确定切换吗？",
    confirmDelete: "确定删除这条备忘录吗？",
    syncTodo: "暂未实现",
    copyCode: "复制代码",
    copied: "已复制",
  },
  en: {
    page: "Memos",
    new: "+ New",
    import: "Import",
    export: "Export",
    delete: "Delete",
    search: "Search memos...",
    loading: "Loading memos…",
    searching: "Searching…",
    searchFail: "Search failed: ",
    noMatch: "No matching memos",
    empty: "No memos yet. Click + to start.",
    untitled: "Untitled memo",
    counting: "Searching…",
    count: (n: number) => `${n} items`,
    close: "Close",
    blankTitle: "Select a memo",
    blankHint: "Or create a new one.",
    title: "Title",
    tags: "Tags:",
    tagsPh: "Comma-separated, e.g. work,important",
    content: "Markdown content",
    contentPh: "Write in Markdown…",
    previewing: "Rendering preview…",
    save: "Save",
    saving: "Saving…",
    edit: "Edit",
    sync: "Split",
    preview: "Preview",
    mode: "View mode",
    newTitle: "New memo",
    imported: "Imported memo",
    importFail: "Import failed: ",
    defaultFile: "memo",
    unsaved: "Memo has unsaved changes. Switch anyway?",
    confirmDelete: "Delete this memo?",
    syncTodo: "Not implemented yet",
    copyCode: "Copy code",
    copied: "Copied",
  },
} as const;

const emptyDraft = (title: string): Memo => {
  const now = new Date().toISOString().replace("T", " ").slice(0, 19);
  return { id: Date.now(), time: now, created: now, modified: now, title, content: "", tags: [] };
};

const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

interface MemoPageProps {
  language?: Lang;
  onDirtyChange?: (dirty: boolean) => void;
}

export function MemoPage({ language = "zh", onDirtyChange }: MemoPageProps) {
  const t = copy[language];
  const [memos, setMemos] = useState<Memo[]>([]);
  const [selected, setSelected] = useState<Memo | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [mode, setMode] = useState<ViewMode>("edit");
  const [preview, setPreview] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const searchToken = useRef(0);
  const renderToken = useRef(0);
  const copyFeedbackTimer = useRef<number | null>(null);

  const runSearch = async (value: string) => {
    const token = ++searchToken.current;
    setSearchError("");
    if (!value.trim()) {
      setSearchResults(null);
      setSearching(false);
      return;
    }
    setSearchResults([]);
    setSearching(true);
    try {
      const results = await invoke<SearchResult[]>("memo_search", { query: value });
      if (token === searchToken.current) setSearchResults(results);
    } catch (reason) {
      if (token === searchToken.current) setSearchError(errorText(reason));
    } finally {
      if (token === searchToken.current) setSearching(false);
    }
  };

  const loadMemos = async (preferredId?: number) => {
    setLoading(true);
    setError("");
    try {
      const values = await invoke<Memo[]>("memo_list");
      setMemos(values);
      setSelected((current) => values.find((memo) => memo.id === (preferredId ?? current?.id)) ?? values[0] ?? null);
      if (query.trim()) await runSearch(query);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadMemos(); }, []);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => { onDirtyChange?.(false); }, [onDirtyChange]);

  useEffect(() => {
    if ((mode !== "preview" && mode !== "split") || !selected) {
      setPreviewLoading(false);
      return;
    }
    const token = ++renderToken.current;
    let active = true;
    const delay = mode === "split" ? 150 : 0;
    // Keep previous HTML while re-rendering to avoid flash (Python debounce behavior).
    if (!preview) setPreviewLoading(true);
    const timer = window.setTimeout(() => {
      const theme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
      invoke<string>("memo_render", { content: selected.content, theme })
        .then((html) => {
          if (active && token === renderToken.current) setPreview(html);
        })
        .catch((reason) => {
          if (active && token === renderToken.current) setError(errorText(reason));
        })
        .finally(() => {
          if (active && token === renderToken.current) setPreviewLoading(false);
        });
    }, delay);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [mode, selected?.content, selected?.id]);

  const visibleMemos: SearchResult[] = query.trim()
    ? (searchResults ?? [])
    : memos.map((memo) => ({ memo, line_number: 1 }));

  const search = async (value: string) => {
    setQuery(value);
    await runSearch(value);
  };

  useEffect(() => () => {
    searchToken.current += 1;
    renderToken.current += 1;
    if (copyFeedbackTimer.current !== null) window.clearTimeout(copyFeedbackTimer.current);
  }, []);

  const copyPreviewCode = async (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>("button[data-memo-code-copy]");
    if (!button) return;
    const block = button.closest<HTMLElement>(".memo-code-block");
    const code = block?.querySelector("pre")?.textContent;
    if (code === undefined || code === null) return;
    try {
      await navigator.clipboard.writeText(code);
      button.textContent = t.copied;
      button.setAttribute("aria-label", t.copied);
      if (copyFeedbackTimer.current !== null) window.clearTimeout(copyFeedbackTimer.current);
      copyFeedbackTimer.current = window.setTimeout(() => {
        button.textContent = t.copyCode;
        button.setAttribute("aria-label", t.copyCode);
      }, 1600);
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const canDiscard = () => !dirty || window.confirm(t.unsaved);

  const selectMemo = (memo: Memo) => {
    if (selected?.id === memo.id || !canDiscard()) return;
    setSelected(memo);
    setDirty(false);
  };

  const createDraft = async () => {
    if (!canDiscard()) return;
    setSaving(true);
    setError("");
    try {
      const draft = emptyDraft(t.newTitle);
      const saved = await invoke<Memo>("memo_create", { memo: draft });
      setDirty(false);
      setMode("edit");
      searchToken.current += 1;
      setSearchResults(null);
      setQuery("");
      await loadMemos(saved.id);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const now = new Date().toISOString().replace("T", " ").slice(0, 19);
      const memo = { ...selected, title: selected.title.trim() || t.defaultFile, time: now, modified: now };
      const exists = memos.some((item) => item.id === memo.id);
      const saved = await invoke<Memo>(exists ? "memo_update" : "memo_create", { memo });
      setDirty(false);
      searchToken.current += 1;
      setSearchResults([]);
      await loadMemos(saved.id);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!selected || !memos.some((memo) => memo.id === selected.id)) return;
    if (!window.confirm(t.confirmDelete)) return;
    setSaving(true);
    setError("");
    try {
      await invoke("memo_delete", { id: selected.id });
      setDirty(false);
      searchToken.current += 1;
      setSearchResults([]);
      await loadMemos();
    } catch (reason) {
      setError(errorText(reason));
      await runSearch(query);
    } finally {
      setSearching(false);
      setSaving(false);
    }
  };

  const patchSelected = (patch: Partial<Memo>) => {
    setSelected((memo) => (memo ? { ...memo, ...patch } : memo));
    setDirty(true);
  };

  const importMemos = async (files: FileList | null) => {
    if (!files?.length) return;
    const imported: Memo[] = [];
    for (const file of Array.from(files)) {
      try {
        const now = new Date().toISOString().replace("T", " ").slice(0, 19);
        imported.push({
          id: Date.now() + imported.length,
          time: now,
          created: now,
          modified: now,
          title: file.name.replace(/\.(md|txt)$/i, "") || t.imported,
          content: await file.text(),
          tags: [],
        });
      } catch (reason) {
        setError(`${t.importFail}${errorText(reason)}`);
      }
    }
    for (const memo of imported) {
      try {
        await invoke("memo_create", { memo });
      } catch (reason) {
        setError(`${t.importFail}${errorText(reason)}`);
      }
    }
    if (imported.length) await loadMemos(imported[imported.length - 1].id);
    if (fileInput.current) fileInput.current.value = "";
  };

  const exportMemo = () => {
    if (!selected) return;
    const title = selected.title || t.defaultFile;
    const body = `# ${title}\n\n${selected.content}`;
    const url = URL.createObjectURL(new Blob([body], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${title.replace(/[\\/:*?"<>|]/g, "_")}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="memo-page" aria-label={t.page}>
      <aside className="memo-rail">
        <header className="memo-rail-header">
          <div className="memo-rail-buttons">
            <button onClick={() => void createDraft()} disabled={saving}>{t.new}</button>
            <button onClick={() => fileInput.current?.click()} disabled={saving}>{t.import}</button>
            <button onClick={exportMemo} disabled={saving || !selected}>{t.export}</button>
            <button className="danger" onClick={() => void remove()} disabled={saving}>{t.delete}</button>
          </div>
          <input ref={fileInput} className="memo-file-input" type="file" accept=".md,.txt,text/markdown,text/plain" multiple onChange={(event) => void importMemos(event.target.files)} />
        </header>
        <label className="memo-search">
          <input value={query} disabled={saving} onChange={(event) => void search(event.target.value)} placeholder={t.search} />
        </label>
        <div className="memo-list">
          {loading && <div className="memo-state">{t.loading}</div>}
          {!loading && searching && <div className="memo-state">{t.searching}</div>}
          {!loading && !searching && searchError && (
            <div className="memo-state memo-search-error" role="alert">{t.searchFail}{searchError}</div>
          )}
          {!loading && !searching && !searchError && visibleMemos.length === 0 && (
            <div className="memo-state">{query ? t.noMatch : t.empty}</div>
          )}
          {!loading && !searching && !searchError && visibleMemos.map((result) => (
            <button
              key={result.memo.id}
              disabled={saving}
              className={`memo-list-item ${selected?.id === result.memo.id ? "active" : ""}`}
              onClick={() => selectMemo(result.memo)}
            >
              <strong>{result.memo.title || t.untitled}</strong>
              <span>{result.memo.tags.map((tag) => `#${tag}`).join(" ") || result.memo.content.split("\n")[0] || ""}</span>
            </button>
          ))}
        </div>
        <div className="memo-count">{searching ? t.counting : t.count(visibleMemos.length)}</div>
      </aside>

      <main className="memo-workspace">
        {error && (
          <div className="memo-error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError("")}>{t.close}</button>
          </div>
        )}
        {!loading && !selected && (
          <div className="memo-blank">
            <span>MP</span>
            <h2>{t.blankTitle}</h2>
            <p>{t.blankHint}</p>
          </div>
        )}
        {selected && (
          <>
            <div className="memo-editor-head">
              <input
                className="memo-title"
                aria-label={t.title}
                disabled={saving}
                value={selected.title}
                onChange={(event) => patchSelected({ title: event.target.value })}
                placeholder={t.title}
              />
              <div className="memo-tags-row">
                <span>{t.tags}</span>
                <input
                  className="memo-tags"
                  aria-label={t.tags}
                  disabled={saving}
                  value={selected.tags.join(", ")}
                  onChange={(event) =>
                    patchSelected({
                      tags: event.target.value
                        .split(/[,，]/)
                        .map((tag) => tag.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder={t.tagsPh}
                />
              </div>
            </div>
            <div className={`memo-content memo-content-${mode}`}>
              {(mode === "edit" || mode === "split") && (
                <textarea
                  className="memo-editor"
                  aria-label={t.content}
                  disabled={saving}
                  value={selected.content}
                  onChange={(event) => patchSelected({ content: event.target.value })}
                  placeholder={t.contentPh}
                  spellCheck
                />
              )}
              {(mode === "split" || mode === "preview") && (
                previewLoading && !preview ? (
                  <div className="memo-preview-state" role="status">{t.previewing}</div>
                ) : (
                  <div className="memo-preview" onClick={copyPreviewCode} dangerouslySetInnerHTML={{ __html: preview }} />
                )
              )}
            </div>
            <footer className="memo-footer">
              <div className="memo-footer-left">
                <button className="primary memo-save" onClick={() => void save()} disabled={saving}>
                  <img src="/assets/icons/save.svg" alt="" />
                  {saving ? t.saving : t.save}
                </button>
              </div>
              <SegmentedControl
                className="memo-mode is-wide"
                ariaLabel={t.mode}
                disabled={saving}
                value={mode}
                options={[
                  ["edit", t.edit],
                  ["split", t.sync],
                  ["preview", t.preview],
                ]}
                onChange={(next) => setMode(next as ViewMode)}
              />
            </footer>
          </>
        )}
      </main>
    </section>
  );
}
