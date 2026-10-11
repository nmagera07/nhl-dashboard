// Highlight videos live on nhl.com; PuckPulse links out to them rather than
// embedding the NHL's player. Only nhl.com links are ever rendered.
const NHL_HOSTS = new Set(["nhl.com", "www.nhl.com"]);

// Accepts the score feed's paths ("/video/...") or full share URLs.
export function nhlVideoUrl(pathOrUrl) {
  if (typeof pathOrUrl !== "string" || !pathOrUrl) return null;
  try {
    const url = new URL(pathOrUrl, "https://www.nhl.com");
    if (url.protocol !== "https:" || !NHL_HOSTS.has(url.hostname) || !url.pathname.startsWith("/video/")) return null;
    return url.href;
  } catch {
    return null;
  }
}
