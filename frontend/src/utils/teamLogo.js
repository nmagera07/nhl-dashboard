// NHL logos come in two versions at the same path: TBL_light.svg for light
// backgrounds and TBL_dark.svg for dark ones (some light versions, like
// Tampa's dark blue, nearly disappear on dark, and some dark ones are
// white). Pick the one for the current theme, which App sets on <html>
// before rendering, so a theme switch re-renders with the right logos.
export function teamLogo(url) {
  if (!url) return url;
  return document.documentElement.dataset.theme === "light"
    ? url.replace(/_dark\.svg$/, "_light.svg")
    : url.replace(/_light\.svg$/, "_dark.svg");
}
