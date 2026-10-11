// The last response for each URL, kept in memory for the session, so going
// back to a page shows what you just saw instantly while a fresh copy loads
// in the background (stale-while-revalidate). Without it, every return to
// Scores rebuilt the page from nothing: blank, then a flash of data.
//
// Once-a-day data (standings, odds, players...) is also saved in
// localStorage, so a returning visitor sees their last copy instantly even
// while the API wakes from a ~20s cold start. Live data (scores, schedules)
// is never saved: yesterday's scores shown as tonight's would be wrong.
const MAX_ENTRIES = 100;
const entries = new Map();

const STORAGE_PREFIX = "puckpulse:response:v1:";
const STORAGE_MAX_AGE_MS = 48 * 60 * 60 * 1000;
const PERSISTED = /\/(standings\/latest|playoff-odds(\/history|\/why)?|players\/leaders|teams\/[A-Z]{3}\/roster|predictions\/track-record|digest\/latest)(\?season_id=\d+)?$/;

export function isPersisted(url) {
  return !!url && PERSISTED.test(url);
}

function storage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null; // blocked (privacy mode, sandboxed iframe)
  }
}

function loadStored(url, now) {
  try {
    const raw = storage()?.getItem(STORAGE_PREFIX + url);
    if (!raw) return undefined;
    const { savedAt, data } = JSON.parse(raw);
    if (now - savedAt > STORAGE_MAX_AGE_MS) {
      storage()?.removeItem(STORAGE_PREFIX + url);
      return undefined;
    }
    return data;
  } catch {
    return undefined;
  }
}

function saveStored(url, data, now) {
  try {
    storage()?.setItem(STORAGE_PREFIX + url, JSON.stringify({ savedAt: now, data }));
  } catch {
    // Quota exceeded or storage blocked: the in-memory copy still works.
  }
}

export function cachedResponse(url, now = Date.now()) {
  if (!url) return undefined;
  if (entries.has(url)) return entries.get(url);
  if (!isPersisted(url)) return undefined;
  const stored = loadStored(url, now);
  if (stored !== undefined) remember(url, stored);
  return stored;
}

function remember(url, data) {
  entries.delete(url); // re-insert so the Map's order tracks recency
  entries.set(url, data);
  if (entries.size > MAX_ENTRIES) entries.delete(entries.keys().next().value);
}

export function rememberResponse(url, data, now = Date.now()) {
  if (!url) return;
  remember(url, data);
  if (isPersisted(url)) saveStored(url, data, now);
}

export function clearResponseCache() {
  entries.clear();
  try {
    const store = storage();
    if (!store) return;
    Object.keys(store).filter((k) => k.startsWith(STORAGE_PREFIX)).forEach((k) => store.removeItem(k));
  } catch {
    // nothing to clear
  }
}
