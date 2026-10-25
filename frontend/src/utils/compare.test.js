import { bestSeason, compareRows, eraAdjust, winner } from "./compare.js";

const season = (id, points, extra = {}) => ({ season_id: id, season_type: "regular_season", points, goals: 10, ...extra });
const MCDAVID = {
  position_code: "C", career_totals: { regular_season: { games_played: 800, goals: 400, assists: 800, points: 1200, plus_minus: 150 },
    playoffs: { games_played: 100, points: 150 } },
  season_history: [season(20222023, 153), season(20232024, 132), { ...season(20222023, 30), season_type: "playoffs" }],
  season_stats: [{ games_played: 10, points: 31 }], war: { war: 0.9 },
};
const GRETZKY = {
  position_code: "C", career_totals: { regular_season: { games_played: 1487, goals: 894, assists: 1963, points: 2857, plus_minus: 520 },
    playoffs: { games_played: 208, points: 382 } },
  season_history: [season(19851986, 215), season(19811982, 212)], season_stats: [], war: null,
};

describe("compare", () => {
  it("finds the best regular season", () => {
    expect(bestSeason(GRETZKY).season_id).toBe(19851986);
    expect(bestSeason(MCDAVID).points).toBe(153); // playoffs don't count
  });

  it("builds skater rows with per-game rates and picks each row's winner", () => {
    const rows = compareRows(MCDAVID, GRETZKY);
    const row = (section, label) => rows.find((r) => r.section === section && r.label === label);
    expect(row("Career", "Points per game").show(row("Career", "Points per game").a)).toBe("1.50");
    expect(winner(row("Career", "Points per game"))).toBe("b");
    expect(row("Best season", "Season").show(19851986)).toBe("85-86");
    expect(winner(row("Best season", "Season"))).toBeNull(); // labels aren't compared
    expect(row("This season", "WAR").b).toBeNull();
    expect(winner(row("This season", "WAR"))).toBeNull(); // nothing to beat
  });

  it("lower is better for goals-against average", () => {
    const g = (gaa) => ({ position_code: "G", career_totals: { regular_season: { games_played: 500, goals_against_avg: gaa } } });
    const row = compareRows(g(2.3), g(2.6)).find((r) => r.label === "Goals against avg");
    expect(winner(row)).toBe("a");
  });
});

describe("eraAdjust", () => {
  const ERA = { reference: 3.08, seasons: { 19851986: 3.97, 20222023: 3.18 } };
  const gretzky = {
    position_code: "C",
    season_history: [
      { season_id: 19851986, season_type: "regular_season", games_played: 80, goals: 52, assists: 163, points: 215, plus_minus: 71 },
      { season_id: 19851986, season_type: "playoffs", games_played: 10, goals: 8, assists: 11, points: 19 },
    ],
    season_stats: [],
  };

  it("rescales each season to today's scoring and rebuilds career totals", () => {
    const adj = eraAdjust(gretzky, ERA);
    const season = adj.season_history[0];
    expect([season.goals, season.assists, season.points]).toEqual([40, 126, 166]);
    expect(season.plus_minus).toBeNull();
    expect(adj.career_totals.regular_season).toEqual({ games_played: 80, goals: 40, assists: 126, points: 166 });
    expect(adj.career_totals.playoffs.points).toBe(Math.round(8 * 3.08 / 3.97) + Math.round(11 * 3.08 / 3.97));
  });

  it("leaves goalies alone, and a season missing from the table unscaled", () => {
    const goalie = { position_code: "G", season_history: [] };
    expect(eraAdjust(goalie, ERA)).toBe(goalie);
    const unknown = eraAdjust({ position_code: "C", season_history: [{ season_id: 19001901, season_type: "regular_season", goals: 10, assists: 5 }] }, ERA);
    expect(unknown.season_history[0].points).toBe(15);
  });
});
