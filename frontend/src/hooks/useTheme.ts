import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

export type Theme = "dark" | "light";
export type ThemeMode = Theme | "auto";

const KEY = "memopaws-theme";
const TRANSITION_CLASS = "theme-transitioning";
const TRANSITION_MS = 200;

function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

function isThemeMode(value: unknown): value is ThemeMode {
  return value === "auto" || isTheme(value);
}

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(KEY);
    return isThemeMode(stored) ? stored : "dark";
  });
  const [system, setSystem] = useState<Theme>(() => systemTheme());
  const themeRef = useRef(theme);
  const explicitThemeChangeRef = useRef(false);

  const apply = (mode: ThemeMode) => {
    document.documentElement.setAttribute("data-theme", mode === "auto" ? systemTheme() : mode);
    localStorage.setItem(KEY, mode);
  };

  const startTransition = () => {
    const root = document.documentElement;
    root.classList.add(TRANSITION_CLASS);
    window.setTimeout(() => root.classList.remove(TRANSITION_CLASS), TRANSITION_MS + 50);
  };

  useEffect(() => {
    let active = true;

    invoke<string>("get_theme")
      .then((value) => {
        if (!active) return;
        const backendMode: ThemeMode = explicitThemeChangeRef.current
          ? themeRef.current
          : isThemeMode(value) ? value : themeRef.current;
        themeRef.current = backendMode;
        setThemeState(backendMode);
        apply(backendMode);
      })
      .catch(() => {
        if (!active) return;
        apply(themeRef.current);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      setSystem(systemTheme());
      if (themeRef.current === "auto") apply("auto");
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const setTheme = (next: ThemeMode | ((previous: ThemeMode) => ThemeMode)) => {
    explicitThemeChangeRef.current = true;
    const nextMode = typeof next === "function" ? next(themeRef.current) : next;
    themeRef.current = nextMode;
    setThemeState(nextMode);
    startTransition();
    apply(nextMode);
    void invoke("set_theme", { theme: nextMode }).catch(() => {});
  };

  const toggleTheme = () => setTheme((previous) => (previous === "dark" ? "light" : "dark"));

  const resolvedTheme: Theme = theme === "auto" ? system : theme;

  return { theme, resolvedTheme, setTheme, toggleTheme };
}
