// Runs before the app (and its CSS) so the page never flashes the wrong
// theme: the saved choice, else the system's. A separate file because the
// Content-Security-Policy allows no inline scripts. Kept in sync with
// src/hooks/useTheme.js.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("pp-theme"); } catch { /* storage blocked: follow the system */ }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  document.documentElement.dataset.theme = theme;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "light" ? "#f4f7fb" : "#0b1424";
})();
