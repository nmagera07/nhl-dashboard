import { isValidISODate, relativeDayLabel, shiftDate, todayISO } from "./dates.js";

describe("dates", () => {
  it("formats today in local time as YYYY-MM-DD", () => {
    expect(todayISO(new Date(2026, 9, 8, 23, 30))).toBe("2026-10-08");
  });

  it("shifts across month and year boundaries", () => {
    expect(shiftDate("2026-10-31", 1)).toBe("2026-11-01");
    expect(shiftDate("2027-01-01", -1)).toBe("2026-12-31");
  });

  it("labels nearby days relative to today", () => {
    expect(relativeDayLabel("2026-10-08", "2026-10-08")).toBe("Today");
    expect(relativeDayLabel("2026-10-07", "2026-10-08")).toBe("Yesterday");
    expect(relativeDayLabel("2026-10-09", "2026-10-08")).toBe("Tomorrow");
    expect(relativeDayLabel("2026-10-12", "2026-10-08")).toMatch(/Oct/);
  });

  it("rejects malformed and impossible dates", () => {
    expect(isValidISODate("2026-10-06")).toBe(true);
    expect(isValidISODate("2026-02-30")).toBe(false);
    expect(isValidISODate("tomorrow")).toBe(false);
    expect(isValidISODate(null)).toBe(false);
  });
});
