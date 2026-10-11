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
