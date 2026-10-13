import { formatPct, neededRecord, pointsPace } from "./pointsPace.js";

const LINE = { p25: 92, p50: 95, p75: 98 };
const team = (extra) => ({ gp: 20, pts: 20, otl: 2, clinch_indicator: null, ...extra });
const points = (r) => 2 * r.w + r.otl;

describe("pointsPace", () => {
  it("works out what a team chasing the line needs", () => {
    const p = pointsPace(LINE, team());
    expect(p.state).toBe("chasing");
    expect(p.ptsNeeded).toBe(75);
    expect(p.gamesRemaining).toBe(62);
    expect(p.reqPct).toBeCloseTo(75 / 124);
    expect(p.pace).toBe(82);
    expect(p.record.w + p.record.l + p.record.otl).toBe(62);
    expect(points(p.record)).toBeGreaterThanOrEqual(75);
    expect(p.early).toBe(false);
  });

  it("is clinched from the NHL indicator", () => {
    expect(pointsPace(LINE, team({ clinch_indicator: "x" })).state).toBe("clinched");
    expect(pointsPace(LINE, team({ clinch_indicator: "z" })).record).toBeNull();
  });

  it("is above the line when it already has the points", () => {
    const p = pointsPace(LINE, team({ gp: 70, pts: 96 }));
    expect(p.state).toBe("above");
    expect(p.ptsNeeded).toBe(0);
  });

  it("is eliminated by the indicator or when even a perfect run falls short", () => {
    expect(pointsPace(LINE, team({ clinch_indicator: "e" })).state).toBe("eliminated");
    const p = pointsPace(LINE, team({ gp: 70, pts: 70 })); // 25 needed in 12 GP
    expect(p.state).toBe("eliminated");
    expect(p.record).toBeNull();
  });

  it("treats needing every point left as still alive (perfect-run boundary)", () => {
    const p = pointsPace(LINE, team({ gp: 70, pts: 71 })); // 24 in 12 GP
    expect(p.reqPct).toBe(1);
    expect(p.state).toBe("chasing");
    expect(p.record).toEqual({ w: 12, l: 0, otl: 0 });
  });

  it("hides when the season is over or there's no line", () => {
    expect(pointsPace(LINE, team({ gp: 82, pts: 90 }))).toBeNull();
    expect(pointsPace(null, team())).toBeNull();
    expect(pointsPace({}, team())).toBeNull();
  });

  it("flags an early estimate and uses the league OT-loss rate under 10 GP", () => {
    const p = pointsPace(LINE, team({ gp: 6, pts: 6, otl: 0 }));
    expect(p.early).toBe(true);
    expect(Math.abs(p.record.otl - Math.round(76 * 0.11))).toBeLessThanOrEqual(1); // 8, less one spare
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
