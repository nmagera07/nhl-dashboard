// The last response for each URL, kept in memory for the session, so going
// back to a page shows what you just saw instantly while a fresh copy loads
// in the background (stale-while-revalidate). Without it, every return to
// Scores rebuilt the page from nothing: blank, then a flash of data.
const MAX_ENTRIES = 100;
const entries = new Map();

export function cachedResponse(url) {
  return url ? entries.get(url) : undefined;
}

export function rememberResponse(url, data) {
  if (!url) return;
  entries.delete(url); // re-insert so the Map's order tracks recency
  entries.set(url, data);
  if (entries.size > MAX_ENTRIES) entries.delete(entries.keys().next().value);
}

export function clearResponseCache() {
  entries.clear();
}
