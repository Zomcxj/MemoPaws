import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useTheme } from "./hooks/useTheme";
import Sidebar, { type Lang } from "./components/Sidebar";
import { RecognizePage } from "./pages/RecognizePage";
import { MemoPage } from "./pages/MemoPage";
import { KeysPage } from "./pages/KeysPage";
import { ClipboardPage } from "./pages/ClipboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import GlobalSearch from "./components/GlobalSearch";
import "./App.css";

type Page = "recognize" | "memo" | "keys" | "clipboard" | "settings";

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("recognize");
  const [memoDirty, setMemoDirty] = useState(false);
  const [language, setLanguage] = useState<Lang>("zh");
  const [searchOpen, setSearchOpen] = useState(false);
  const { theme, resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    let active = true;
    invoke<Record<string, unknown>>("get_config")
      .then((raw) => {
        if (!active) return;
        const next = raw.language === "en" ? "en" : "zh";
        setLanguage(next);
        window.localStorage.setItem("language", next);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void invoke("show_main_window_when_ready").catch(() => {});
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const changeLanguage = (next: Lang) => {
    setLanguage(next);
    window.localStorage.setItem("language", next);
  };

  const navigate = (page: Page) => {
    if (page === currentPage) return;
    if (currentPage === "memo" && memoDirty && !window.confirm(language === "en" ? "Memo has unsaved changes. Leave anyway?" : "备忘录有未保存修改，确定离开吗？")) return;
    if (currentPage === "memo") setMemoDirty(false);
    setCurrentPage(page);
  };

  const navigateRef = useRef<(page: Page) => void>(() => {});
  useEffect(() => {
    navigateRef.current = navigate;
  });

  useEffect(() => {
    const unlisten = listen<string>("global-shortcut", (event) => {
      switch (event.payload) {
        case "capture":
          // 页面切换是异步的，此时监听器未挂载会丢事件；用待办标记让识别页挂载后补触发
          (window as unknown as { __memoPendingCapture?: boolean }).__memoPendingCapture = true;
          navigateRef.current("recognize");
          window.dispatchEvent(new CustomEvent("memopaws-capture"));
          break;
        case "new_memo":
          navigateRef.current("memo");
          break;
        case "global_search":
          setSearchOpen(true);
          break;
        case "canvas_fit":
          navigateRef.current("recognize");
          window.dispatchEvent(new CustomEvent("canvas_fit"));
          break;
        case "toggle_clipboard":
          navigateRef.current("clipboard");
          break;
      }
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case "recognize": return <RecognizePage language={language} />;
      case "memo": return <MemoPage language={language} onDirtyChange={setMemoDirty} renderTheme={resolvedTheme} />;
      case "keys": return <KeysPage language={language} />;
      case "clipboard": return <ClipboardPage language={language} />;
      case "settings": return <SettingsPage theme={theme} onThemeChange={setTheme} onLanguageChange={changeLanguage} />;
    }
  };

  return (
    <div className="app-shell">
      <div className="app-layout">
        <Sidebar
          currentPage={currentPage}
          onNavigate={navigate}
          language={language}
        />
        <main className="app-content">{renderPage()}</main>
      </div>
      {searchOpen && <GlobalSearch language={language} onClose={() => setSearchOpen(false)} onNavigate={navigate} />}
    </div>
  );
}
