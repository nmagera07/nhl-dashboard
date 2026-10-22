import { API_BASE, INTELLIGENCE_BASE } from "../config.js";

// The AI service scales to zero when idle, and waking it takes ~15-25s.
// Pages ping it (and the API, for the database) shortly after loading, and
// again when the Ask button is hovered, pressed, or opened, so it's awake by
// the time a question is asked. At most once per WARM_EVERY_MS: it stays up
// for a few minutes after a request, at Azure's idle rate (a fraction of a
// cent per wake), so it only runs while people are on the site.
const WARM_EVERY_MS = 4 * 60 * 1000;
let lastWarm = -Infinity;

export function warmUpChat(now = Date.now(), fetchImpl = globalThis.fetch) {
  if (now - lastWarm < WARM_EVERY_MS) return false;
  lastWarm = now;
  // /health on the API touches the database too, which the first answer needs.
  for (const url of [`${INTELLIGENCE_BASE}/health`, `${API_BASE}/health`]) {
    fetchImpl(url, { cache: "no-store" }).catch(() => {});
  }
  return true;
}

export function resetWarmUp() {
  lastWarm = -Infinity;
}
