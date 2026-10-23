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

  // Liquid-glass toggle: independent of dark/light/auto, layered on top of the existing theme.
  // Local persistence is enough; the backend config has no field for it (a pure display preference).
  const [glass, setGlass] = useState(() => window.localStorage.getItem("memopaws-glass") === "on");
  useEffect(() => {
    document.documentElement.setAttribute("data-glass", glass ? "on" : "off");
    window.localStorage.setItem("memopaws-glass", glass ? "on" : "off");
    // The DWM acrylic layer must follow the toggle in sync: when statically set in tauri.conf.json,
    // turning the toggle off leaves title-bar areas unreachable by CSS permanently glassy.
    void invoke("set_glass_effect", { enabled: glass }).catch(() => {});
  }, [glass]);

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
          // Page switches are asynchronous and the listener may not be mounted yet, which would drop
          // the event; a pending flag lets the recognize page re-trigger after mount.
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

  // Update notifications: the backend poll emits update-available when it finds a newer version; only the version is recorded for badge display.
  const [latestVersion, setLatestVersion] = useState<string | null>(null);

  useEffect(() => {
    const unlisten = listen<{ version: string; currentVersion: string }>("update-available", (event) => {
      setLatestVersion(event.payload.version);
    });
    return () => {
      void unlisten.then((stop) => stop());
    };
  }, []);

  useEffect(() => {
    // update-available is emitted once per process (the backend dedupes via notified): if the 15s
    // cold-start first check happens before the listener registers, the event is dropped and the
    // badge is missing for the whole session. A proactive mount query closes the badge chain; silent
    // on null (no update/check failed) or invoke failure, so offline users are not disturbed.
    void invoke<{ latestVersion: string | null; hasUpdate: boolean }>("latest_release_version")
      .then((check) => {
        if (check?.hasUpdate && check.latestVersion) setLatestVersion(check.latestVersion);
      })
      .catch(() => {});
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case "recognize": return <RecognizePage language={language} />;
      case "memo": return <MemoPage language={language} onDirtyChange={setMemoDirty} renderTheme={resolvedTheme} />;
      case "keys": return <KeysPage language={language} />;
      case "clipboard": return <ClipboardPage language={language} />;
      case "settings": return <SettingsPage theme={theme} onThemeChange={setTheme} onLanguageChange={changeLanguage} onUpdateFound={setLatestVersion} glass={glass} onGlassChange={setGlass} />;
    }
  };

  return (
    <div className="app-shell">
      <div className="app-layout">
        <Sidebar
          currentPage={currentPage}
          onNavigate={navigate}
          language={language}
          updateAvailable={latestVersion !== null}
        />
        <main className="app-content">{renderPage()}</main>
      </div>
      {searchOpen && <GlobalSearch language={language} onClose={() => setSearchOpen(false)} onNavigate={navigate} />}
    </div>
  );
}
