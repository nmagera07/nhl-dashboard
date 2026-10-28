import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

// public/push-sw.js runs in the service worker, not the app: load the real
// file against a fake `self` and fire a push at it.
function loadWorker({ subscription = { endpoint: "https://fcm.googleapis.com/fcm/send/abc" }, fetchImpl } = {}) {
  const listeners = {};
  const shown = [];
  const self = {
    location: { origin: "https://puckpulse.io" },
    addEventListener: (type, fn) => (listeners[type] = fn),
    registration: {
      showNotification: async (title, options) => shown.push({ title, ...options }),
      pushManager: { getSubscription: async () => subscription },
    },
  };
  const fetch = vi.fn(fetchImpl || (async () => ({ ok: true })));
  const source = readFileSync(resolve(process.cwd(), "public/push-sw.js"), "utf8"); // vitest runs from frontend/
  new Function("self", "fetch", "caches", "atob", source)(self, fetch, undefined, atob);

  const push = async (payload) => {
    let done;
    listeners.push({ data: { json: () => payload, text: () => "" }, waitUntil: (p) => (done = p) });
    await done;
  };
  return { push, shown, fetch };
}

describe("push-sw.js", () => {
  it("shows the alert and reports it arrived, with its event key", async () => {
    const { push, shown, fetch } = loadWorker();
    await push({ title: "🚨 FLA goal!", body: "FLA 4, WPG 1", tag: "goal-1", url: "/games/1", key: "goal:2026020194:FLA:4-1" });

    expect(shown[0]).toMatchObject({ title: "🚨 FLA goal!", body: "FLA 4, WPG 1", tag: "goal-1" });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toMatch(/\/push\/receipts$/);
    expect(JSON.parse(init.body)).toEqual({ endpoint: "https://fcm.googleapis.com/fcm/send/abc", key: "goal:2026020194:FLA:4-1" });
  });

  it("still shows the alert when the receipt can't be sent", async () => {
    const { push, shown } = loadWorker({ fetchImpl: async () => { throw new Error("offline"); } });
    await push({ title: "Final: FLA 4, WPG 1", key: "final:2026020194" });
    expect(shown).toHaveLength(1);
  });

  it("sends no receipt for a push without a key (older payloads)", async () => {
    const { push, shown, fetch } = loadWorker();
    await push({ title: "PuckPulse" });
    expect(shown).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });
});
