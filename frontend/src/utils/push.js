// Web Push in the browser: whether it's possible here, and subscribing or
// unsubscribing this device for a team's goal and final-score alerts.
import { API_BASE } from "../config.js";

export function isStandalone() {
  return window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

// "ready" | "ios-install" (iPhone: only home-screen apps get push) |
// "denied" (blocked in settings) | "unsupported"
export function pushSupport() {
  if (typeof window === "undefined") return "unsupported";
  if (isIOS() && !isStandalone()) return "ios-install";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return "ready";
}

// VAPID public key: base64url -> bytes, as PushManager.subscribe() wants.
function keyBytes(base64url) {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

async function registration() {
  return navigator.serviceWorker.ready;
}

export async function currentSubscription() {
  if (pushSupport() !== "ready") return null;
  return (await registration()).pushManager.getSubscription();
}

async function save(subscription, teams) {
  const { endpoint, keys } = subscription.toJSON();
  const res = await fetch(`${API_BASE}/push/subscriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint, keys, teams }),
  });
  if (!res.ok) throw new Error(`Couldn't save the subscription (${res.status})`);
}

// Ask permission (must be called from a tap), subscribe, and register the
// teams with the API. Returns the new permission state.
export async function enableAlerts(teams) {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission;
  const config = await fetch(`${API_BASE}/push/config`).then((r) => r.json());
  if (!config.enabled) throw new Error("Notifications aren't set up on the server yet.");
  const reg = await registration();
  const subscription =
    (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(config.vapid_public_key) }));
  await save(subscription, teams);
  return permission;
}

// Re-register when the followed team changes.
export async function updateAlertTeams(teams) {
  const subscription = await currentSubscription();
  if (subscription) await save(subscription, teams);
}

export async function disableAlerts() {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await fetch(`${API_BASE}/push/subscriptions`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint: subscription.endpoint }),
  }).catch(() => {});
  await subscription.unsubscribe();
}
