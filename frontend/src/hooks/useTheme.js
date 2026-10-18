import { useEffect, useState } from "react";

// Light or dark. Until someone picks, the page follows the system setting
// (and keeps following it); once they toggle, the choice is saved on this
// device. public/theme-init.js applies the same rule before first paint.
const KEY = "pp-theme";
const BAR_COLORS = { light: "#f4f7fb", dark: "#0a0b0f" };

function saved() {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

const systemTheme = () => (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark");

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = BAR_COLORS[theme];
}

export function useTheme() {
  const [choice, setChoice] = useState(saved);
  const [system, setSystem] = useState(systemTheme);
  const theme = choice || system;
  // Set on <html> during render (not after), so components rendering now
  // (team logos) already see the new theme.
  if (typeof document !== "undefined" && document.documentElement.dataset.theme !== theme) applyTheme(theme);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: light)");
    if (!query) return undefined;
    const onChange = () => setSystem(query.matches ? "light" : "dark");
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);

  const toggle = () => {
    const next = theme === "light" ? "dark" : "light";
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* not saved; it still switches for this visit */
    }
    setChoice(next);
  };
  return [theme, toggle];
}
