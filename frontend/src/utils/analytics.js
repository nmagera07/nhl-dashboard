// Product analytics: Umami Cloud (cookieless, no personal data; the
// tracker is self-hosted as /stats.js, see index.html). Page views are
// automatic, including SPA route changes. track() adds a named event for
// the features we want usage counts on. It's a no-op when the tracker
// isn't loaded: localhost, PR previews, Do Not Track, or an ad blocker.
export function track(name, data) {
  try {
    globalThis.umami?.track(name, data);
  } catch {
    // Analytics must never break the app.
  }
}
