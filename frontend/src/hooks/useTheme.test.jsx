import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTheme } from "./useTheme.js";

function mockSystem(light) {
  window.matchMedia = vi.fn().mockReturnValue({ matches: light, addEventListener: vi.fn(), removeEventListener: vi.fn() });
}

describe("useTheme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("follows the system until someone picks", () => {
    mockSystem(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("pp-theme")).toBeNull();
  });

  it("toggling switches the page and remembers the choice", () => {
    mockSystem(false);
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]());
    expect(result.current[0]).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("pp-theme")).toBe("light");
  });

  it("toggling back to the system's theme follows the phone again", () => {
    mockSystem(false);
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]()); // light: saved
    act(() => result.current[1]()); // dark again, as the phone is: not saved
    expect(result.current[0]).toBe("dark");
    expect(localStorage.getItem("pp-theme")).toBeNull();
  });

  it("a saved choice beats the system", () => {
    mockSystem(true);
    localStorage.setItem("pp-theme", "dark");
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("dark");
  });
});
