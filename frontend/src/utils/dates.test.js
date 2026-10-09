import { gameTimeLabel, isValidISODate, monthGrid, monthOf, relativeDayLabel, shiftDate, shiftMonth, todayISO } from "./dates.js";

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

describe("month helpers", () => {
  it("steps months across year boundaries", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2027-01", -1)).toBe("2026-12");
  });

  it("builds a Sunday-first grid with leading blanks", () => {
    // October 1, 2026 is a Thursday: 4 blanks (Sun-Wed), then 31 days.
    const grid = monthGrid("2026-10");
    expect(grid.slice(0, 4)).toEqual([null, null, null, null]);
    expect(grid[4]).toBe("2026-10-01");
    expect(grid.at(-1)).toBe("2026-10-31");
    expect(grid).toHaveLength(35);
  });

  it("gets the month of a date", () => {
    expect(monthOf("2026-10-06")).toBe("2026-10");
  });

  it("labels a game's start time relative to today", () => {
    const at = (y, m, d, h) => new Date(y, m - 1, d, h).toISOString();
    expect(gameTimeLabel(at(2026, 10, 9, 19), "2026-10-09")).toMatch(/^Today 7:00\sPM$/);
    expect(gameTimeLabel(at(2026, 10, 10, 19), "2026-10-09")).toMatch(/^Tomorrow 7:00\sPM$/);
    expect(gameTimeLabel(at(2026, 10, 14, 19), "2026-10-09")).toMatch(/^Wed, Oct 14 7:00\sPM$/);
    expect(gameTimeLabel(null)).toBe("TBD");
  });
});
