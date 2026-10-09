import { act, renderHook } from "@testing-library/react";
import { useFavoriteTeam } from "./useFavoriteTeam.js";

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
