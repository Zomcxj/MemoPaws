import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
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

const emptyDraft = (): Memo => {
  const now = new Date().toISOString().replace("T", " ").slice(0, 19);
  return { id: Date.now(), time: now, created: now, modified: now, title: "新备忘录", content: "", tags: [] };
};

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

interface MemoPageProps {
  onDirtyChange?: (dirty: boolean) => void;
}

export function MemoPage({ onDirtyChange }: MemoPageProps) {
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
    setPreview("");
    setPreviewLoading(true);
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
    return () => { active = false; };
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
  }, []);

  const canDiscard = () => !dirty || window.confirm("当前备忘录有未保存修改，确定放弃吗？");

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
      const draft = emptyDraft();
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
      const memo = { ...selected, title: selected.title.trim() || "备忘录", time: now, modified: now };
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
    const warning = dirty ? "未保存修改将一并丢失。" : "此操作无法撤销。";
    if (!window.confirm(`删除“${selected.title || "备忘录"}”？${warning}`)) return;
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
    setSelected((memo) => memo ? { ...memo, ...patch } : memo);
    setDirty(true);
  };

  const importMemos = async (files: FileList | null) => {
    if (!files?.length) return;
    const imported: Memo[] = [];
    for (const file of Array.from(files)) {
      try {
        const now = new Date().toISOString().replace("T", " ").slice(0, 19);
        imported.push({ id: Date.now() + imported.length, time: now, created: now, modified: now, title: file.name.replace(/\.(md|txt)$/i, "") || "导入的备忘录", content: await file.text(), tags: [] });
      } catch (reason) {
        setError(`导入失败：${errorText(reason)}`);
      }
    }
    for (const memo of imported) {
      try { await invoke("memo_create", { memo }); } catch (reason) { setError(`导入失败：${errorText(reason)}`); }
    }
    if (imported.length) await loadMemos(imported[imported.length - 1].id);
    if (fileInput.current) fileInput.current.value = "";
  };

  const exportMemo = () => {
    if (!selected) return;
    const body = `# ${selected.title || "备忘录"}\n\n${selected.content}`;
    const url = URL.createObjectURL(new Blob([body], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(selected.title || "备忘录").replace(/[\\/:*?"<>|]/g, "_")}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="memo-page" aria-label="备忘录">
      <aside className="memo-rail">
        <header className="memo-rail-header">
          <div className="memo-rail-buttons">
            <button onClick={() => void createDraft()} disabled={saving}>+ 新建</button>
            <button onClick={() => fileInput.current?.click()} disabled={saving}>导入</button>
            <button onClick={exportMemo} disabled={saving || !selected}>导出</button>
            <button className="danger" onClick={() => void remove()} disabled={saving}>删除</button>
          </div>
          <input ref={fileInput} className="memo-file-input" type="file" accept=".md,.txt,text/markdown,text/plain" multiple onChange={(event) => void importMemos(event.target.files)} />
        </header>
        <label className="memo-search"><input value={query} disabled={saving} onChange={(event) => void search(event.target.value)} placeholder="搜索备忘录..." /></label>
        <div className="memo-list">
          {loading && <div className="memo-state">正在整理备忘录…</div>}
          {!loading && searching && <div className="memo-state">正在搜索备忘录…</div>}
          {!loading && !searching && searchError && <div className="memo-state memo-search-error" role="alert">搜索失败：{searchError}</div>}
          {!loading && !searching && !searchError && visibleMemos.length === 0 && <div className="memo-state">{query ? "没有匹配的备忘录" : "还没有备忘录，点击 + 开始记录"}</div>}
          {!loading && !searching && !searchError && visibleMemos.map((result) => (
            <button key={result.memo.id} disabled={saving} className={`memo-list-item ${selected?.id === result.memo.id ? "active" : ""}`} onClick={() => selectMemo(result.memo)}>
              <strong>{result.memo.title || "未命名备忘录"}</strong>
              <span>{result.memo.tags.map((tag) => `#${tag}`).join(" ") || result.memo.content.split("\n")[0] || ""}</span>
            </button>
          ))}
        </div>
        <div className="memo-count">{searching ? "搜索中…" : `${visibleMemos.length} 条`}</div>
      </aside>

      <main className="memo-workspace">
        {error && <div className="memo-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}
        {!loading && !selected && <div className="memo-blank"><span>MP</span><h2>选择一条备忘录</h2><p>或创建一条新的记录。</p></div>}
        {selected && (
          <>
            <div className="memo-editor-head">
              <input className="memo-title" aria-label="标题" disabled={saving} value={selected.title} onChange={(event) => patchSelected({ title: event.target.value })} placeholder="标题" />
              <div className="memo-tags-row">
                <span>标签:</span>
                <input className="memo-tags" aria-label="标签" disabled={saving} value={selected.tags.join(", ")} onChange={(event) => patchSelected({ tags: event.target.value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean) })} placeholder="逗号分隔，如：工作,重要" />
              </div>
            </div>
            <div className={`memo-content memo-content-${mode}`}>
              {(mode === "edit" || mode === "split") && <textarea className="memo-editor" aria-label="Markdown 内容" disabled={saving} value={selected.content} onChange={(event) => patchSelected({ content: event.target.value })} placeholder="用 Markdown 写下此刻…" spellCheck />}
              {(mode === "split" || mode === "preview") && (previewLoading ? <div className="memo-preview-state" role="status">正在生成预览…</div> : <div className="memo-preview" dangerouslySetInnerHTML={{ __html: preview }} />)}
            </div>
            <footer className="memo-footer">
              <div className="memo-footer-left">
                <button className="primary memo-save" onClick={() => void save()} disabled={saving}><img src="/assets/icons/save.svg" alt="" />{saving ? "保存中…" : "保存"}</button>
              </div>
              <div className="memo-mode" aria-label="视图模式">
                <button disabled={saving} className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")}>编辑</button>
                <button disabled={saving} type="button" className={mode === "split" ? "active" : ""} onClick={() => setError("暂未实现")}>同步</button>
                <button disabled={saving} className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}>预览</button>
              </div>
            </footer>
          </>
        )}
      </main>
    </section>
  );
}
