import { createContext, useContext, useEffect, useState } from "react";
import { flushSync } from "react-dom";

export type Theme = "light" | "dark";
const STORAGE_KEY = "arabamfiyat-theme";

function stored(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

const system = (): Theme => window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";

/** The visitor's choice, or the system setting until they make one. index.html applies it before first paint. */
export function initialTheme(): Theme {
  return stored() ?? system();
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme | undefined) ?? initialTheme());
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    // Follow system changes only while the visitor has not chosen explicitly.
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const follow = () => { if (!stored()) setTheme(system()); };
    media?.addEventListener?.("change", follow);
    return () => media?.removeEventListener?.("change", follow);
  }, [theme]);
  // Printing always uses the light palette, charts included.
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true));
    const after = () => setPrinting(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => { window.removeEventListener("beforeprint", before); window.removeEventListener("afterprint", after); };
  }, []);
  const toggle = () => setTheme((current) => {
    const next = current === "dark" ? "light" : "dark";
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* private mode: the choice lasts this visit */ }
    return next;
  });
  return { theme, chartTheme: (printing ? "light" : theme) as Theme, toggle };
}

/** SVG chart colours; chart libraries set them as attributes, where CSS variables are not reliable. */
export const CHART_COLORS: Record<Theme, {
  all: string; clean: string; grid: string; cursor: string; dotFill: string; muted: string; range: string; median: string; asking: string; highlight: string;
}> = {
  light: { all: "#2563eb", clean: "#16875b", grid: "#e7edf5", cursor: "#98a2b3", dotFill: "#fff", muted: "#b9c9df", range: "#dff2e9", median: "#123154", asking: "#e8692e", highlight: "#78a7f5" },
  dark: { all: "#6f9cf3", clean: "#45c08a", grid: "#243044", cursor: "#6f7e94", dotFill: "#151e2d", muted: "#46597a", range: "#16362a", median: "#dde4ee", asking: "#f08a4b", highlight: "#8fb6f7" },
};

export const ThemeContext = createContext<Theme>("light");
export const useChartColors = () => CHART_COLORS[useContext(ThemeContext)];
