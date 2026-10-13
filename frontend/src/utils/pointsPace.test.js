import { formatPct, neededRecord, pointsPace } from "./pointsPace.js";

const LINE = { p25: 92, p50: 95, p75: 98 };
const team = (extra) => ({ gp: 20, pts: 20, otl: 2, clinch_indicator: null, ...extra });
const points = (r) => 2 * r.w + r.otl;

describe("pointsPace", () => {
  // 2026-27 onward: 84-game seasons (the API sends season_games).
  it("works out what a team chasing the line needs, over 84 games", () => {
    const p = pointsPace(LINE, team(), 84);
    expect(p.state).toBe("chasing");
    expect(p.ptsNeeded).toBe(75);
    expect(p.gamesRemaining).toBe(64);
    expect(p.reqPct).toBeCloseTo(75 / 128);
    expect(p.pace).toBe(84); // a .500 points % over 84 games
    expect(p.record.w + p.record.l + p.record.otl).toBe(64);
    expect(points(p.record)).toBeGreaterThanOrEqual(75);
    expect(p.early).toBe(false);
  });

  it("uses the team's real games left from the schedule when given", () => {
    expect(pointsPace(LINE, team({ games_left: 61 }), 84).gamesRemaining).toBe(61);
  });

  it("still handles an 82-game season", () => {
    const p = pointsPace(LINE, team(), 82);
    expect(p.gamesRemaining).toBe(62);
    expect(p.pace).toBe(82);
  });

  it("is clinched from the NHL indicator", () => {
    expect(pointsPace(LINE, team({ clinch_indicator: "x" }), 84).state).toBe("clinched");
    expect(pointsPace(LINE, team({ clinch_indicator: "z" }), 84).record).toBeNull();
  });

  it("is above the line when it already has the points", () => {
    const p = pointsPace(LINE, team({ gp: 70, pts: 96 }), 84);
    expect(p.state).toBe("above");
    expect(p.ptsNeeded).toBe(0);
  });

  it("is eliminated by the indicator or when even a perfect run falls short", () => {
    expect(pointsPace(LINE, team({ clinch_indicator: "e" }), 84).state).toBe("eliminated");
    const p = pointsPace(LINE, team({ gp: 72, pts: 70 }), 84); // 25 needed in 12 GP (24 max)
    expect(p.state).toBe("eliminated");
    expect(p.record).toBeNull();
  });

  it("treats needing every point left as still alive (perfect-run boundary)", () => {
    const p = pointsPace(LINE, team({ gp: 72, pts: 71 }), 84); // 24 in 12 GP
    expect(p.reqPct).toBe(1);
    expect(p.state).toBe("chasing");
    expect(p.record).toEqual({ w: 12, l: 0, otl: 0 });
  });

  it("hides when the season is over or there's no line", () => {
    expect(pointsPace(LINE, team({ gp: 84, pts: 90 }), 84)).toBeNull();
    expect(pointsPace(null, team(), 84)).toBeNull();
    expect(pointsPace({}, team(), 84)).toBeNull();
  });

  it("flags an early estimate and uses the league OT-loss rate under 10 GP", () => {
    const p = pointsPace(LINE, team({ gp: 6, pts: 6, otl: 0 }), 84);
    expect(p.early).toBe(true);
    expect(p.gamesRemaining).toBe(78);
    expect(Math.abs(p.record.otl - Math.round(78 * 0.11))).toBeLessThanOrEqual(1);
    expect(points(p.record)).toBe(89);
  });
});

describe("neededRecord", () => {
  it("is always enough points and minimal", () => {
    for (let gr = 1; gr <= 30; gr++) {
      for (let need = 1; need <= 2 * gr; need++) {
        for (const share of [0, 0.11, 0.3, 1]) {
          const r = neededRecord(need, gr, share);
          expect(r.w + r.l + r.otl).toBe(gr);
          expect(Math.min(r.w, r.l, r.otl)).toBeGreaterThanOrEqual(0);
          expect(points(r)).toBeGreaterThanOrEqual(need);
          expect(points(r)).toBeLessThanOrEqual(need + 1); // never more than one spare point
        }
      }
    }
  });

  it("is null when even winning out isn't enough", () => {
    expect(neededRecord(25, 12, 0.11)).toBeNull();
  });
});

describe("formatPct", () => {
  it("formats like NHL points percentages", () => {
    expect(formatPct(0.586)).toBe(".586");
    expect(formatPct(1)).toBe("1.000");
    expect(formatPct(null)).toBe("—");
  });
});
