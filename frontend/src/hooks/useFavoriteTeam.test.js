import { act, renderHook } from "@testing-library/react";
import { useFavoriteTeam, useFollowedTeams } from "./useFavoriteTeam.js";

describe("useFavoriteTeam", () => {
  afterEach(() => window.localStorage.clear());

  it("remembers the team and keeps every reader in sync", () => {
    const a = renderHook(() => useFavoriteTeam());
    const b = renderHook(() => useFavoriteTeam());
    expect(a.result.current[0]).toBeNull();

    act(() => a.result.current[1]("PIT"));

    expect(b.result.current[0]).toBe("PIT");
    expect(window.localStorage.getItem("nhl-dash:favorite-team")).toBe("PIT");

    act(() => b.result.current[1](null));

    expect(a.result.current[0]).toBeNull();
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });

    const { result } = renderHook(() => useFavoriteTeam());

    expect(result.current[0]).toBeNull();
    expect(() => act(() => result.current[1]("PIT"))).not.toThrow();
    vi.restoreAllMocks();
  });
});

describe("useFollowedTeams", () => {
  afterEach(() => window.localStorage.clear());

  it("a visitor's one saved team becomes their first followed team", () => {
    window.localStorage.setItem("nhl-dash:favorite-team", "PIT");
    const { result } = renderHook(() => useFollowedTeams());
    expect(result.current[0]).toEqual(["PIT"]);
  });

  it("follows up to five, main first; makeMain and unfollow reorder", () => {
    const { result } = renderHook(() => useFollowedTeams());
    for (const t of ["PIT", "FLA", "TBL", "VGK", "BOS", "NYR"]) act(() => result.current[1].follow(t));
    expect(result.current[0]).toEqual(["PIT", "FLA", "TBL", "VGK", "BOS"]); // NYR: past the limit
    act(() => result.current[1].makeMain("TBL"));
    expect(result.current[0]).toEqual(["TBL", "PIT", "FLA", "VGK", "BOS"]);
    act(() => result.current[1].unfollow("TBL"));
    expect(result.current[0]).toEqual(["PIT", "FLA", "VGK", "BOS"]);
    expect(window.localStorage.getItem("nhl-dash:favorite-team")).toBe("PIT"); // the main team, for older code
  });

  it("ignores junk in storage", () => {
    window.localStorage.setItem("nhl-dash:followed-teams", '["PIT", 5, "<script>", "fla"]');
    const { result } = renderHook(() => useFollowedTeams());
    expect(result.current[0]).toEqual(["PIT"]);
  });
});
