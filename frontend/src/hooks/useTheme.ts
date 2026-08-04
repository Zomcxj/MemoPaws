import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

export type Theme = "dark" | "light";

const KEY = "memopaws-theme";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(KEY);
    return (stored === "light" || stored === "dark") ? stored : "dark";
  });
  const themeRef = useRef(theme);
  const explicitThemeChangeRef = useRef(false);

  useEffect(() => {
    let active = true;

    invoke<string>("get_theme")
      .then((value) => {
        if (!active) return;
        const backendTheme = explicitThemeChangeRef.current
          ? themeRef.current
          : value === "light" || value === "dark" ? value : themeRef.current;
        themeRef.current = backendTheme;
        setThemeState(backendTheme);
        document.documentElement.setAttribute("data-theme", backendTheme);
        localStorage.setItem(KEY, backendTheme);
      })
      .catch(() => {
        if (!active) return;
        document.documentElement.setAttribute("data-theme", themeRef.current);
        localStorage.setItem(KEY, themeRef.current);
      });

    return () => {
      active = false;
    };
  }, []);

  const setTheme = (next: Theme | ((previous: Theme) => Theme)) => {
    explicitThemeChangeRef.current = true;
    const nextTheme = typeof next === "function" ? next(themeRef.current) : next;
    themeRef.current = nextTheme;
    setThemeState(nextTheme);
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem(KEY, nextTheme);
    void invoke("set_theme", { theme: nextTheme }).catch(() => {});
  };

  const toggleTheme = () => setTheme(prev => prev === "dark" ? "light" : "dark");

  return { theme, setTheme, toggleTheme };
}
