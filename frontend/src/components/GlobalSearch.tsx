import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Lang } from "./Sidebar";
import "./GlobalSearch.css";

interface SearchResult {
  source: string;
  id: number;
  title: string;
  text: string;
  time: string;
}

interface Props {
  language: Lang;
  onClose: () => void;
  onNavigate: (page: "recognize" | "memo" | "keys" | "clipboard" | "settings") => void;
}

const labels = {
  zh: { title: "全局搜索", placeholder: "搜索剪切板和历史记录", loading: "搜索中...", empty: "没有找到匹配内容", error: "搜索失败，请重试", clipboard: "剪切板", history: "历史记录" },
  en: { title: "Global Search", placeholder: "Search clipboard and history", loading: "Searching...", empty: "No matching content", error: "Search failed. Try again.", clipboard: "Clipboard", history: "History" },
};

export default function GlobalSearch({ language, onClose, onNavigate }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef(0);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const t = labels[language];

  useEffect(() => {
    inputRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(false);
      return;
    }

    const requestId = ++requestRef.current;
    setLoading(true);
    setError(false);
    const timer = window.setTimeout(() => {
      invoke<SearchResult[]>("global_search", { query: trimmed })
        .then((next) => {
          if (requestId === requestRef.current) setResults(next);
        })
        .catch(() => {
          if (requestId === requestRef.current) {
            setResults([]);
            setError(true);
          }
        })
        .finally(() => {
          if (requestId === requestRef.current) setLoading(false);
        });
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const selectResult = (result: SearchResult) => {
    onClose();
    onNavigate(result.source === "clipboard" ? "clipboard" : "recognize");
  };

  return (
    <div className="global-search-overlay" role="presentation" onMouseDown={onClose}>
      <section className="global-search-dialog" role="dialog" aria-modal="true" aria-labelledby="global-search-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="global-search-header">
          <h2 id="global-search-title">{t.title}</h2>
          <button type="button" className="global-search-close" aria-label={language === "en" ? "Close search" : "关闭搜索"} onClick={onClose}>×</button>
        </div>
        <input ref={inputRef} className="global-search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.placeholder} />
        <div className="global-search-status" aria-live="polite">
          {loading && <span>{t.loading}</span>}
          {!loading && error && <span className="global-search-error">{t.error}</span>}
          {!loading && !error && query.trim() && results.length === 0 && <span>{t.empty}</span>}
        </div>
        <div className="global-search-results">
          {results.map((result) => (
            <button type="button" className="global-search-result" key={`${result.source}-${result.id}`} onClick={() => selectResult(result)}>
              <span className="global-search-result-meta"><strong>{result.source === "clipboard" ? t.clipboard : t.history}</strong><time>{result.time}</time></span>
              <span className="global-search-result-title">{result.title}</span>
              <span className="global-search-result-text">{result.text}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
