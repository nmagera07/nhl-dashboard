import { describe, it, expect } from "vitest";
import { formatEv, formatPct, formatPrice, formatSpread } from "./odds.js";

describe("odds formatting", () => {
  it("formats American prices and spreads with a real minus sign", () => {
    expect(formatPrice(150)).toBe("+150");
    expect(formatPrice(-150)).toBe("−150");
    expect(formatPrice(null)).toBe("—");
    expect(formatSpread(-1.5)).toBe("−1.5");
    expect(formatSpread(1.5)).toBe("+1.5");
  });

  it("formats chances and expected returns", () => {
    expect(formatPct(0.663)).toBe("66%");
    expect(formatEv(0.062)).toBe("+6%");
    expect(formatEv(-0.04)).toBe("−4%");
  });
});
