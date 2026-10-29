import { describe, it, expect } from "vitest";
import { betLabel, grade, summarize } from "./myBets.js";

const final = (away, home, state = "OFF") => ({ gameState: state, awayTeam: { score: away }, homeTeam: { score: home } });
const bet = (over) => ({ id: "7:moneyline:home", gameId: 7, away: "PIT", home: "COL", market: "moneyline", side: "home", line: null, price: -150, ...over });
const CLOSE = {
  snapshot: "close",
  moneyline: { home: { market: 0.64, price: -175 }, away: { market: 0.36, price: 160 } },
  puck_line: { home_spread: -1.5, home: { market: 0.4, price: 140 }, away: { market: 0.6, price: -160 } },
  total: { line: 6, over: { market: 0.5, price: -105 }, under: { market: 0.5, price: -115 } },
};

describe("myBets", () => {
  it("labels bets as the Bets tab does", () => {
    expect(betLabel(bet())).toBe("COL");
    expect(betLabel(bet({ market: "puck_line", side: "away", line: 1.5 }))).toBe("PIT +1.5");
    expect(betLabel(bet({ market: "total", side: "under", line: 6.5 }))).toBe("Under 6.5");
  });

  it("waits for the final", () => {
    expect(grade(bet(), final(1, 3, "LIVE"), CLOSE)).toBeNull();
    expect(grade(bet(), undefined, CLOSE)).toBeNull();
  });

  it("grades the moneyline and measures CLV against the close", () => {
    // -150 pays 0.6667 per unit; at the close the books gave COL 64%: 0.64 x 1.6667 - 1 = +6.7%.
    expect(grade(bet(), final(1, 3), CLOSE)).toEqual({ outcome: "win", units: 0.6667, clv: 0.0667, closePrice: -175 });
    expect(grade(bet({ side: "away", price: 170 }), final(1, 3), CLOSE)).toEqual({ outcome: "loss", units: -1, clv: -0.028, closePrice: 160 });
  });

  it("grades the puck line from the bet's side, and pushes a whole-number total", () => {
    const pl = bet({ market: "puck_line", side: "away", line: 1.5, price: -160 });
    expect(grade(pl, final(2, 3), CLOSE).outcome).toBe("win"); // lost by 1, covered +1.5
    expect(grade(pl, final(1, 3), CLOSE).outcome).toBe("loss");
    expect(grade(bet({ market: "total", side: "over", line: 6, price: -105 }), final(2, 4), CLOSE)).toMatchObject({ outcome: "push", units: 0 });
  });

  it("gives no CLV when the line moved or there was no closing snapshot", () => {
    expect(grade(bet({ market: "total", side: "over", line: 6.5, price: 110 }), final(4, 3), CLOSE)).toMatchObject({ outcome: "win", clv: null, closePrice: null });
    expect(grade(bet(), final(1, 3), { ...CLOSE, snapshot: "morning" }).clv).toBeNull();
  });

  it("sums the record, units, and CLV", () => {
    const s = summarize([
      bet({ result: { outcome: "win", units: 0.5, clv: 0.04 } }),
      bet({ result: { outcome: "loss", units: -1, clv: -0.02 } }),
      bet({ result: { outcome: "push", units: 0, clv: null } }),
      bet(),
    ]);
    expect(s).toMatchObject({ wins: 1, losses: 1, pushes: 1, graded: 3, units: -0.5, beatClose: 1, clvCount: 2, clv: 0.01 });
    expect(s.roi).toBeCloseTo(-0.1667);
  });
});
