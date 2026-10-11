import { cachedResponse, clearResponseCache, rememberResponse } from "./responseCache.js";

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
