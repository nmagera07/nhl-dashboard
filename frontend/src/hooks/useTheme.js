import { useState } from "react";

// Light or dark. Dark for everyone until they pick light, which is saved on
// this device; toggling back to dark clears it. public/theme-init.js applies
// the same rule before first paint.
const KEY = "pp-theme";
const BAR_COLORS = { light: "#eef2f7", dark: "#0b1220" };

function saved() {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = BAR_COLORS[theme];
}

export function useTheme() {
  const [theme, setTheme] = useState(saved);
  // Set on <html> during render (not after), so components rendering now
  // (team logos) already see the new theme.
  if (typeof document !== "undefined" && document.documentElement.dataset.theme !== theme) applyTheme(theme);

  const toggle = () => {
    const next = theme === "light" ? "dark" : "light";
    try {
      if (next === "light") localStorage.setItem(KEY, "light");
      else localStorage.removeItem(KEY);
    } catch {
      /* not saved; it still switches for this visit */
    }
    setTheme(next);
  };
  return [theme, toggle];
}
