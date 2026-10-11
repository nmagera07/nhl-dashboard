import { API_BASE, INTELLIGENCE_BASE } from "../config.js";

// Both backends scale to zero when idle, and waking them (plus the
// database) takes ~20-30s. Opening the chat pings them in the background,
// so they're mostly awake by the time the first question is typed. At most
// once per WARM_EVERY_MS: they stay up for a few minutes after a request.
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
