// Push notification handling, loaded into the app's service worker
// (vite.config.js -> workbox.importScripts). Payloads come from
// backend/notify_live_games.py: { title, body, url, tag }.

self.addEventListener("push", (event) => {
  let data;
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "PuckPulse", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
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
    })
  );
});

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
      // again with the teams the app last saved (src/utils/push.js).
      const saved = await (await caches.open("pp-alerts")).match("/alert-teams");
      const teams = saved ? await saved.json() : null;
      if (Array.isArray(teams) && teams.length) await post("/push/subscriptions", { endpoint, keys, teams });
    })().catch(() => {})
  );
});
