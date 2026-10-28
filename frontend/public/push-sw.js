// Push notification handling, loaded into the app's service worker
// (vite.config.js -> workbox.importScripts). Payloads come from
// backend/notify_live_games.py: { title, body, url, tag, key }.

self.addEventListener("push", (event) => {
  let data;
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "PuckPulse", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(Promise.all([
    self.registration.showNotification(data.title || "PuckPulse", {
      body: data.body || "",
      icon: "/pwa-192x192.png",
      // The status-bar icon: Android uses only its shape (alpha), so it is a
      // white mark on transparent; the full-color icon came out as a block.
      badge: "/icons/puckpulse-mono-96.png",
      // Tags are per goal (and per final), so each one is its own
      // notification; renotify only matters if a tag ever repeats.
      tag: data.tag,
      renotify: Boolean(data.tag),
      data: { url: data.url || "/" },
    }),
    receipt(data.key),
  ]));
});

// Tell the API the alert arrived (POST /push/receipts), so the delivery log
// shows how long each one took: on 2026-10-27 a sleeping phone got four of
// six goal alerts only after they had expired. Never fails the push.
function receipt(key) {
  if (!key) return Promise.resolve();
  return self.registration.pushManager
    .getSubscription()
    .then((subscription) => subscription && post("/push/receipts", { endpoint: subscription.endpoint, key }))
    .catch(() => {});
}

// Tapping the notification opens that game's box score, reusing an open
// app window if there is one.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin);
      if (open) return open.navigate(url).then((w) => (w || open).focus());
      return self.clients.openWindow(url);
    })
  );
});

// The browser can replace a push subscription on its own (keys rotated,
// subscription expired). Alerts then went to the old endpoint until the
// app was opened or alerts were toggled off and on (2026-10-25: three
// goals and a final missed). Move the saved subscription to the new one.
const API = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";

function keyBytes(base64url) {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

const post = (path, body) =>
  fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    (async () => {
      let subscription = event.newSubscription;
      if (!subscription) {
        const config = await fetch(`${API}/push/config`).then((r) => r.json());
        if (!config.enabled) return;
        subscription = await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(config.vapid_public_key),
        });
      }
      const { endpoint, keys } = subscription.toJSON();
      if (event.oldSubscription) {
        const moved = await post("/push/subscriptions/renew", { old_endpoint: event.oldSubscription.endpoint, endpoint, keys });
        if (moved.ok) return;
      }
      // Chrome often doesn't say which subscription was replaced: subscribe
      // again with the teams and alert settings the app last saved
      // (src/utils/push.js; older versions saved only the teams).
      const cache = await caches.open("pp-alerts");
      const saved = (await cache.match("/alert-settings")) || (await cache.match("/alert-teams"));
      const settings = saved ? await saved.json() : null;
      const body = Array.isArray(settings) ? { teams: settings } : settings;
      if (body && Array.isArray(body.teams) && body.teams.length) await post("/push/subscriptions", { ...body, endpoint, keys });
    })().catch(() => {})
  );
});
