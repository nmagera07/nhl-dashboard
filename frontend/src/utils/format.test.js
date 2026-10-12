import { formatSigned, formatToi } from "./format.js";
import { shortDateLabel } from "./dates.js";

describe("formatSigned", () => {
  it("signs, rounds, and never shows −0", () => {
    expect(formatSigned(1.234)).toBe("+1.2");
    expect(formatSigned(-0.31, 2)).toBe("−0.31");
    expect(formatSigned(-0.01)).toBe("0.0");
    expect(formatSigned(5, 0)).toBe("+5");
    expect(formatSigned(null)).toBe("—");
  });
});

describe("shortDateLabel", () => {
  it("reads the date straight from the string", () => {
    expect(shortDateLabel("2026-10-09")).toBe("Oct 9");
    expect(shortDateLabel("2026-12-31T23:30:00Z")).toBe("Dec 31");
    expect(shortDateLabel(null)).toBeNull();
    expect(shortDateLabel("soon")).toBeNull();
  });
});

describe("formatToi", () => {
  it("shows minutes:seconds", () => {
    expect(formatToi(1190)).toBe("19:50");
    expect(formatToi(605)).toBe("10:05");
    expect(formatToi(null)).toBe("—");
  });
});
