import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTheme } from "./useTheme.js";

describe("useTheme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("is dark for everyone until someone picks light, even on a light-mode phone", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("pp-theme")).toBeNull();
  });

  it("toggling switches the page and remembers light", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]());
    expect(result.current[0]).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("pp-theme")).toBe("light");
  });

  it("toggling back to dark forgets the choice", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]());
    act(() => result.current[1]());
    expect(result.current[0]).toBe("dark");
    expect(localStorage.getItem("pp-theme")).toBeNull();
  });

  it("a saved light choice is kept", () => {
    localStorage.setItem("pp-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("light");
  });
});
