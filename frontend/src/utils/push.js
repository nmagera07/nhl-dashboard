// Web Push in the browser: whether it's possible here, and subscribing or
// unsubscribing this device for a team's goal and final-score alerts.
import { API_BASE } from "../config.js";
import { track } from "./analytics.js";

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

// This device's alert settings: what to be alerted about, and followed
// teams to leave out ("muted"). Saved with the subscription, so the
// notifier filters before sending.
const PREFS_KEY = "pp-alert-prefs";
export const DEFAULT_ALERT_PREFS = { starts: true, goals: true, goals_against: true, finals: true, value: false, muted: [] };

export function alertPrefs() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(PREFS_KEY) || "{}");
    return { ...DEFAULT_ALERT_PREFS, ...saved, muted: Array.isArray(saved.muted) ? saved.muted : [] };
  } catch {
    return { ...DEFAULT_ALERT_PREFS };
  }
}

export function setAlertPrefs(prefs) {
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // not saved here; the server still has them for this visit's save
  }
}

// The subscription body's settings: followed teams minus muted ones (never
// none: muting is stopped at the last team), and the five switches.
export function alertSettings(teams, prefs = alertPrefs()) {
  const kept = teams.filter((t) => !prefs.muted.includes(t));
  return { teams: kept.length ? kept : teams, starts: prefs.starts, goals: prefs.goals, goals_against: prefs.goals_against, finals: prefs.finals, value: prefs.value };
}

async function save(subscription, teams) {
  const { endpoint, keys } = subscription.toJSON();
  const settings = alertSettings(teams);
  const res = await fetch(`${API_BASE}/push/subscriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint, keys, ...settings }),
  });
  if (!res.ok) throw new Error(`Couldn't save the subscription (${res.status})`);
  rememberSettings(settings);
}

// The service worker can't read localStorage; if the browser replaces the
// subscription while the app is closed, it re-subscribes with these
// (public/push-sw.js, pushsubscriptionchange).
async function rememberSettings(settings) {
  try {
    const cache = await caches.open("pp-alerts");
    await cache.delete("/alert-teams"); // before alert settings: the teams alone
    if (settings) await cache.put("/alert-settings", new Response(JSON.stringify(settings), { headers: { "Content-Type": "application/json" } }));
    else await cache.delete("/alert-settings");
  } catch {
    // no Cache API here: the app re-saves the subscription the next time it opens anyway
  }
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
  track("goal-alerts-on", { team: teams?.[0] });
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
  await rememberSettings(null);
}
