import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_ALERT_PREFS, alertSettings, disableAlerts, setAlertPrefs, updateAlertTeams } from "./push.js";

// The service worker re-subscribes with the teams the app last saved
// (public/push-sw.js, pushsubscriptionchange), so saving must leave them in the Cache API.
describe("alert teams for the service worker", () => {
  let store;
  const subscription = {
    endpoint: "https://fcm.googleapis.com/fcm/send/abc",
    toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/abc", keys: { p256dh: "p", auth: "a" } }),
    unsubscribe: vi.fn(),
  };

  beforeEach(() => {
    store = new Map();
    globalThis.caches = {
      open: async () => ({
        put: async (key, response) => store.set(key, await response.json()),
        delete: async (key) => store.delete(key),
      }),
    };
    globalThis.PushManager = function PushManager() {};
    globalThis.Notification = { permission: "granted" };
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ pushManager: { getSubscription: async () => subscription } }) },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.caches;
  });

  it("saving the subscription remembers its settings; turning alerts off forgets them", async () => {
    await updateAlertTeams(["FLA"]);
    const settings = { teams: ["FLA"], starts: true, goals: true, goals_against: true, finals: true, value: false };
    await vi.waitFor(() => expect(store.get("/alert-settings")).toEqual(settings));
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ endpoint: subscription.endpoint, keys: { p256dh: "p", auth: "a" }, ...settings });

    await disableAlerts();
    expect(store.has("/alert-settings")).toBe(false);
  });

  it("sends the device's alert settings, leaving out muted teams", async () => {
    setAlertPrefs({ starts: false, goals: true, goals_against: false, finals: true, value: true, muted: ["VGK"] });
    await updateAlertTeams(["PIT", "FLA", "VGK"]);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ teams: ["PIT", "FLA"], starts: false, goals_against: false, value: true });
    localStorage.clear();
  });

  it("never sends an empty team list", () => {
    expect(alertSettings(["PIT"], { ...DEFAULT_ALERT_PREFS, muted: ["PIT"] }).teams).toEqual(["PIT"]);
  });
});
