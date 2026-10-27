import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { disableAlerts, updateAlertTeams } from "./push.js";

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

  it("saving the subscription remembers its teams; turning alerts off forgets them", async () => {
    await updateAlertTeams(["FLA"]);
    await vi.waitFor(() => expect(store.get("/alert-teams")).toEqual(["FLA"]));
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ endpoint: subscription.endpoint, teams: ["FLA"] });

    await disableAlerts();
    expect(store.has("/alert-teams")).toBe(false);
  });
});
