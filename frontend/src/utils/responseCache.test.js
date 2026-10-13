import { API_BASE } from "../config.js";
import { cachedResponse, clearResponseCache, isPersisted, rememberResponse } from "./responseCache.js";

describe("responseCache", () => {
  it("remembers the latest response per URL", () => {
    rememberResponse("/a", 1);
    rememberResponse("/a", 2);
    expect(cachedResponse("/a")).toBe(2);
    expect(cachedResponse("/missing")).toBeUndefined();
    expect(cachedResponse(null)).toBeUndefined();
  });

  it("drops the least recently stored URL past 100 entries", () => {
    for (let i = 0; i <= 100; i++) rememberResponse(`/u${i}`, i);
    expect(cachedResponse("/u0")).toBeUndefined();
    expect(cachedResponse("/u100")).toBe(100);
    clearResponseCache();
    expect(cachedResponse("/u100")).toBeUndefined();
  });
});

describe("responseCache across visits", () => {
  const API = "https://api.test";
  const forget = () => {
    // Simulate a new visit: memory gone, localStorage kept.
    const saved = { ...localStorage };
    clearResponseCache();
    Object.entries(saved).forEach(([k, v]) => localStorage.setItem(k, v));
  };

  it("brings back once-a-day data on the next visit", () => {
    rememberResponse(`${API}/standings/latest`, [{ team_abbrev: "PIT" }], 1000);
    forget();
    expect(cachedResponse(`${API}/standings/latest`, 2000)).toEqual([{ team_abbrev: "PIT" }]);
  });

  it("never saves live data like scores and schedules", () => {
    rememberResponse(`${API}/games/today`, { games: [1] });
    rememberResponse(`${API}/teams/PIT/schedule`, { upcoming: [] });
    forget();
    expect(cachedResponse(`${API}/games/today`)).toBeUndefined();
    expect(cachedResponse(`${API}/teams/PIT/schedule`)).toBeUndefined();
  });

  it("drops saved copies older than two days", () => {
    rememberResponse(`${API}/playoff-odds`, [1], 0);
    forget();
    expect(cachedResponse(`${API}/playoff-odds`, 49 * 60 * 60 * 1000)).toBeUndefined();
  });

  it("keeps working when storage is full or broken", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(() => rememberResponse(`${API}/players/leaders`, [1])).not.toThrow();
    expect(cachedResponse(`${API}/players/leaders`)).toEqual([1]); // still in memory
    spy.mockRestore();

    localStorage.setItem("puckpulse:response:v1:" + `${API}/digest/latest`, "{not json");
    expect(cachedResponse(`${API}/digest/latest`)).toBeUndefined();
  });

  it("knows which URLs are once-a-day", () => {
    expect(isPersisted(`${API}/playoff-odds/history?season_id=20252026`)).toBe(true);
    expect(isPersisted(`${API}/teams/PIT/roster`)).toBe(true);
    expect(isPersisted(`${API}/season-sim/scenario?team=PIT`)).toBe(false);
  });
});

describe("responseCache and the Players table view", () => {
  const LEGACY = `puckpulse:response:v1:${API_BASE}/players/leaders`;
  const TABLE_URL = `${API_BASE}/players/leaders?view=table`;

  it("persists the ?view=table URL under its own v1 key", () => {
    expect(isPersisted(TABLE_URL)).toBe(true);
    rememberResponse(TABLE_URL, [{ player_id: 1 }], 1000);
    expect(JSON.parse(localStorage.getItem(`puckpulse:response:v1:${TABLE_URL}`)).data).toEqual([{ player_id: 1 }]);
  });

  it("removes the legacy full /players/leaders copy on load, and keeps the rest", async () => {
    localStorage.setItem(LEGACY, JSON.stringify({ savedAt: Date.now(), data: [1] }));
    localStorage.setItem(`puckpulse:response:v1:${API_BASE}/standings/latest`, JSON.stringify({ savedAt: Date.now(), data: [2] }));
    vi.resetModules();
    await import("./responseCache.js");
    expect(localStorage.getItem(LEGACY)).toBeNull();
    expect(localStorage.getItem(`puckpulse:response:v1:${API_BASE}/standings/latest`)).not.toBeNull();
  });

  it("loads without localStorage", async () => {
    const spy = vi.spyOn(globalThis, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.resetModules();
    await expect(import("./responseCache.js")).resolves.toBeDefined();
    spy.mockRestore();
  });
});
