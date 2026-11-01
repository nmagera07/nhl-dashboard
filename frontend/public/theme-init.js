// Runs before the app (and its CSS) so the page never flashes the wrong
// theme: the saved choice, else dark (the default since the 2026-11 redesign). A separate file because the
// Content-Security-Policy allows no inline scripts. Kept in sync with
// src/hooks/useTheme.js.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("pp-theme"); } catch { /* storage blocked: dark */ }
  if (theme !== "light") theme = "dark";
  document.documentElement.dataset.theme = theme;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "light" ? "#eef2f7" : "#0b1220";
})();
