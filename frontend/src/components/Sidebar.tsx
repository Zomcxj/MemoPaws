import { useState } from "react";
import "./Sidebar.css";

export type Page = "recognize" | "memo" | "keys" | "clipboard" | "settings";
export type Lang = "zh" | "en";

interface SidebarProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
  language?: Lang;
}

const labels: Record<Lang, Record<Page, string>> = {
  zh: { settings: "设置", recognize: "贴图识别", clipboard: "剪切板", memo: "备忘录", keys: "密钥" },
  en: { settings: "Settings", recognize: "Recognition", clipboard: "Clipboard", memo: "Notes", keys: "Keys" },
};

const navItems = [
  { page: "settings" as Page, icon: "settings.svg" },
  { page: "recognize" as Page, icon: "camera.svg" },
  { page: "clipboard" as Page, icon: "clipboard.svg" },
  { page: "memo" as Page, icon: "memo.svg" },
  { page: "keys" as Page, icon: "key.svg" },
];

export default function Sidebar({ currentPage, onNavigate, language = "zh" }: SidebarProps) {
  const [expanded, setExpanded] = useState(true);
  const t = labels[language] || labels.zh;
  const collapseLabel = language === "en" ? (expanded ? "Collapse sidebar" : "Expand sidebar") : (expanded ? "折叠侧边栏" : "展开侧边栏");

  return (
    <aside className={`sidebar ${expanded ? "expanded" : "collapsed"}`}>
      <button
        className="sidebar-toggle"
        type="button"
        aria-label={collapseLabel}
        title={collapseLabel}
        onClick={() => setExpanded((value) => !value)}
      >
        <img src="/assets/icons/panel-left.svg" alt="" aria-hidden="true" />
      </button>
      <nav className="sidebar-nav">
        {navItems.map(({ page, icon }) => {
          const label = t[page];
          return (
            <button
              key={page}
              className={`sidebar-item ${currentPage === page ? "active" : ""}`}
              onClick={() => onNavigate(page)}
              title={!expanded ? label : undefined}
            >
              <img src={`/assets/icons/${icon}`} alt="" aria-hidden="true" />
              <span className="sidebar-label">{label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
