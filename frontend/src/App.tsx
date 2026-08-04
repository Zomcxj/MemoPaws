import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTheme } from "./hooks/useTheme";
import Sidebar, { type Lang } from "./components/Sidebar";
import { RecognizePage } from "./pages/RecognizePage";
import { MemoPage } from "./pages/MemoPage";
import { KeysPage } from "./pages/KeysPage";
import { ClipboardPage } from "./pages/ClipboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import "./App.css";

type Page = "recognize" | "memo" | "keys" | "clipboard" | "settings";

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("recognize");
  const [memoDirty, setMemoDirty] = useState(false);
  const [language, setLanguage] = useState<Lang>("zh");
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

  const renderPage = () => {
    switch (currentPage) {
      case "recognize": return <RecognizePage />;
      case "memo": return <MemoPage onDirtyChange={setMemoDirty} />;
      case "keys": return <KeysPage />;
      case "clipboard": return <ClipboardPage />;
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
    </div>
  );
}
