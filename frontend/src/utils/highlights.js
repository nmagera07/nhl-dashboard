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

const toSeconds = (clock) => {
  const [m, s] = String(clock || "").split(":").map(Number);
  return Number.isFinite(m) && Number.isFinite(s) ? m * 60 + s : null;
};

// The NHL clip of the goal at `second` (game time), from the box score's scoring summary.
export function goalClip(scoring, second) {
  const period = Math.floor(second / 1200) + 1;
  const into = second - (period - 1) * 1200;
  const goal = (scoring || [])
    .filter((p) => p.periodDescriptor?.number === period)
    .flatMap((p) => p.goals || [])
    .find((g) => toSeconds(g.timeInPeriod) === into);
  return nhlVideoUrl(goal?.highlightClipSharingUrl);
}
