import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useTheme } from "./hooks/useTheme";
import Sidebar, { type Lang } from "./components/Sidebar";
import { RecognizePage } from "./pages/RecognizePage";
import { MemoPage } from "./pages/MemoPage";
import { KeysPage } from "./pages/KeysPage";
import { ClipboardPage } from "./pages/ClipboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import GlobalSearch from "./components/GlobalSearch";
import FloatingWidget from "./components/FloatingWidget";
import "./App.css";

type Page = "recognize" | "memo" | "keys" | "clipboard" | "settings";

// The floating window loads the same bundle; the window label decides what renders.
const isFloatingWindow = () => {
  try {
    if (new URLSearchParams(window.location.search).get("window") === "floating") return true;
    return getCurrentWindow().label === "floating";
  } catch {
    return false;
  }
};

export default function App() {
  const [floating] = useState(isFloatingWindow);
  const [currentPage, setCurrentPage] = useState<Page>("recognize");
  const [memoDirty, setMemoDirty] = useState(false);
  const [language, setLanguage] = useState<Lang>("zh");
  const [searchOpen, setSearchOpen] = useState(false);
  const [pasteOcrRequest, setPasteOcrRequest] = useState(0);
  const { theme, setTheme } = useTheme();

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
    if (floating) return;
    const frame = window.requestAnimationFrame(() => {
      void invoke("show_main_window_when_ready").catch(() => {});
    });
    return () => window.cancelAnimationFrame(frame);
  }, [floating]);

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

  // Intents arrive from the floating widget; the main window owns the navigation.
  useEffect(() => {
    const unlisten = listen<string>("floating-intent", (event) => {
      switch (event.payload) {
        case "capture":
          navigateRef.current("recognize");
          window.dispatchEvent(new CustomEvent("memopaws-capture"));
          break;
        case "paste_ocr":
          navigateRef.current("recognize");
          setPasteOcrRequest((request) => request + 1);
          break;
        case "memo":
          navigateRef.current("memo");
          break;
        case "clipboard":
          navigateRef.current("clipboard");
          break;
        case "keys":
          navigateRef.current("keys");
          break;
        case "settings":
          navigateRef.current("settings");
          break;
        case "search":
          setSearchOpen(true);
          break;
      }
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case "recognize": return <RecognizePage language={language} pasteOcrRequest={pasteOcrRequest} />;
      case "memo": return <MemoPage language={language} onDirtyChange={setMemoDirty} />;
      case "keys": return <KeysPage language={language} />;
      case "clipboard": return <ClipboardPage language={language} />;
      case "settings": return <SettingsPage theme={theme} onThemeChange={setTheme} onLanguageChange={changeLanguage} />;
    }
  };

  if (floating) return <FloatingWidget language={language} />;

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
