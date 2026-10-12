import { shortDate, timeAgo } from "./timeAgo.js";

describe("timeAgo", () => {
  const now = Date.parse("2026-10-12T12:00:00Z");
  it("reads like a feed", () => {
    expect(timeAgo("2026-10-12T11:55:00Z", now)).toBe("5m ago");
    expect(timeAgo("2026-10-12T12:00:00Z", now)).toBe("1m ago");
    expect(timeAgo("2026-10-12T09:00:00Z", now)).toBe("3h ago");
    expect(timeAgo("2026-10-11T06:00:00Z", now)).toBe("Yesterday");
    expect(timeAgo("2026-10-08T12:00:00Z", now)).toBe("Oct 8");
    expect(timeAgo("not a date", now)).toBe("");
  });
  it("formats return dates", () => {
    expect(shortDate("2026-10-16")).toBe("Oct 16");
    expect(shortDate(null)).toBeNull();
  });
});
