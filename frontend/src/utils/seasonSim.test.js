import { cutLine, makeRng, playoffPicture, simulateMany, simulateSeason, winProbability } from "./seasonSim.js";

const MODEL = { home_edge: 0.264, scale: 1.47, ot_probability: 0.221, shootout_share_of_ot: 0.32 };

// Two 4-team divisions in one conference: 3 per division + 2 wild cards = 8 make it.
function inputs(overrides = {}) {
  const teams = {};
  ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1"].forEach((t) => {
    teams[t] = {
      points: 0, wins: 0, losses: 0, ot_losses: 0, regulation_wins: 0, row: 0,
      division: t === "C1" ? "Central" : t[0] === "A" ? "Atlantic" : "Metropolitan", conference: t === "C1" ? "Western" : "Eastern",
      rating: 0, rating_sd: 0, ...(overrides[t] || {}),
    };
  });
  const games = [];
  const names = Object.keys(teams).filter((t) => t !== "C1");
  for (let round = 0; round < 4; round++) names.forEach((h, i) => names.slice(i + 1).forEach((a) => games.push([`2026-11-${10 + round}`, h, a])));
  return { model: MODEL, teams, games };
}

describe("winProbability", () => {
  it("matches the Python model: home ice is worth a bit over half a game", () => {
    expect(winProbability(0, 0, MODEL)).toBeCloseTo(1 / (1 + Math.exp(-0.264 / 1.47)), 10);
    expect(winProbability(1, 0, MODEL)).toBeGreaterThan(winProbability(0, 0, MODEL));
  });
});

describe("simulateSeason", () => {
  it("plays every game once, keeping records and points consistent", () => {
    const sim = inputs();
    const { records } = simulateSeason(sim, makeRng(1));

    Object.entries(records).filter(([t]) => t !== "C1").forEach(([, r]) => {
      expect(r.wins + r.losses + r.ot_losses).toBe(28); // 7 opponents x 4
      expect(r.points).toBe(2 * r.wins + r.ot_losses);
      expect(r.row).toBeLessThanOrEqual(r.wins);
      expect(r.regulation_wins).toBeLessThanOrEqual(r.row);
    });
    const totalWins = Object.values(records).reduce((s, r) => s + r.wins, 0);
    expect(totalWins).toBe(sim.games.length);
  });

  it("is reproducible with a seed and logs the focus team's games", () => {
    const sim = inputs();
    const a = simulateSeason(sim, makeRng(42), "A1");
    const b = simulateSeason(sim, makeRng(42), "A1");

    expect(a.records).toEqual(b.records);
    expect(a.log).toHaveLength(28);
    expect(a.log.filter((g) => g.result === "W")).toHaveLength(a.records.A1.wins);
    expect(a.log.every((g) => g.result !== "OTL" || g.decided !== "REG")).toBe(true);
  });

  it("strong teams win more", () => {
    const sim = inputs({ A1: { rating: 1.5 }, B4: { rating: -1.5 } });
    const { points } = simulateMany(sim, "A1", 200, makeRng(3));
    const weak = simulateMany(sim, "B4", 200, makeRng(3));

    expect(points[100]).toBeGreaterThan(weak.points[100] + 15);
  });
});

describe("playoffPicture", () => {
  const rec = (division, points, extra = {}) => ({ division, conference: "Eastern", points, wins: 0, regulation_wins: 0, row: 0, ...extra });

  it("seeds the top 3 per division, then 2 wild cards", () => {
    const picture = playoffPicture({
      A1: rec("Atlantic", 100), A2: rec("Atlantic", 95), A3: rec("Atlantic", 90), A4: rec("Atlantic", 89), A5: rec("Atlantic", 70),
      M1: rec("Metropolitan", 99), M2: rec("Metropolitan", 80), M3: rec("Metropolitan", 79), M4: rec("Metropolitan", 85), M5: rec("Metropolitan", 60),
    });

    expect(picture.A1.seed).toBe("A1");
    expect(picture.M4).toEqual({ divisionRank: 2, seed: "M2" });
    expect(picture.A4.seed).toBe("WC1");
    expect(picture.M3.seed).toBe("WC2");
    expect(picture.A5.seed).toBeNull();
  });

  it("breaks ties on regulation wins, then ROW, then wins", () => {
    const picture = playoffPicture({
      X: rec("Atlantic", 90, { regulation_wins: 30 }),
      Y: rec("Atlantic", 90, { regulation_wins: 31 }),
    });
    expect(picture.Y.divisionRank).toBe(1);
  });
});

describe("cutLine", () => {
  it("is the points of the last team in from that conference", () => {
    const result = simulateSeason(inputs(), makeRng(9));
    const inPoints = Object.entries(result.picture)
      .filter(([t, p]) => p.seed && result.records[t].conference === "Eastern")
      .map(([t]) => result.records[t].points);

    expect(cutLine(result, "A1")).toBe(Math.min(...inPoints));
  });
});
