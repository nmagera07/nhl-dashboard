// In-browser season simulator: plays out the rest of the regular season
// with the same model as backend/simulate_playoff_odds.py (team strength
// drawn from each team's rating, logistic win probability with home ice,
// overtime and shootout points, NHL playoff format and tiebreakers). The
// model's constants come from the API with the inputs, so the two can't
// drift apart.

// Small, fast, seedable PRNG (mulberry32), so tests can be deterministic.
export function makeRng(seed = Math.floor(Math.random() * 2 ** 32)) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(rng, mean, sd) {
  // Box-Muller
  const u = 1 - rng();
  const v = rng();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function winProbability(home, away, model) {
  return 1 / (1 + Math.exp(-(home - away + model.home_edge) / model.scale));
}

// Points, then regulation wins, then regulation + OT wins, then wins.
function compareTeams(a, b) {
  return b.points - a.points || b.regulation_wins - a.regulation_wins || b.row - a.row || b.wins - a.wins;
}

// Top 3 in each division, then 2 wild cards per conference. Returns
// { [abbrev]: { seed: "M2" | "WC1" | ..., divisionRank } } for every team.
export function playoffPicture(records) {
  const divisions = {};
  Object.entries(records).forEach(([abbrev, r]) => (divisions[r.division] ||= []).push({ abbrev, ...r }));
  const out = {};
  const leftovers = {};
  Object.entries(divisions).forEach(([division, teams]) => {
    teams.sort(compareTeams);
    teams.forEach((t, i) => {
      out[t.abbrev] = { divisionRank: i + 1, seed: i < 3 ? `${division[0]}${i + 1}` : null };
      if (i >= 3) (leftovers[t.conference] ||= []).push(t);
    });
  });
  Object.values(leftovers).forEach((teams) => {
    teams.sort(compareTeams);
    teams.slice(0, 2).forEach((t, i) => (out[t.abbrev].seed = `WC${i + 1}`));
  });
  return out;
}

// One full season. `focus` (optional) also returns that team's game log.
export function simulateSeason(inputs, rng = makeRng(), focus = null) {
  const { model, teams, games } = inputs;
  const strength = {};
  const records = {};
  Object.entries(teams).forEach(([abbrev, t]) => {
    strength[abbrev] = gauss(rng, t.rating, t.rating_sd);
    records[abbrev] = {
      points: t.points, wins: t.wins, losses: t.losses, ot_losses: t.ot_losses,
      regulation_wins: t.regulation_wins, row: t.row, division: t.division, conference: t.conference,
    };
  });

  const log = [];
  for (const [date, home, away] of games) {
    if (!records[home] || !records[away]) continue;
    const homeWins = rng() < winProbability(strength[home], strength[away], model);
    const [winner, loser] = homeWins ? [home, away] : [away, home];
    const w = records[winner];
    const l = records[loser];
    w.points += 2;
    w.wins += 1;
    let decided = "REG";
    if (rng() < model.ot_probability) {
      l.points += 1;
      l.ot_losses += 1;
      if (rng() >= model.shootout_share_of_ot) {
        w.row += 1;
        decided = "OT";
      } else {
        decided = "SO";
      }
    } else {
      l.losses += 1;
      w.regulation_wins += 1;
      w.row += 1;
    }
    if (focus && (home === focus || away === focus)) {
      const won = winner === focus;
      log.push({
        date,
        home: home === focus,
        opponent: home === focus ? away : home,
        result: won ? "W" : decided === "REG" ? "L" : "OTL",
        decided,
      });
    }
  }

  return { records, picture: playoffPicture(records), log };
}

// Many seasons for one team: how its points and playoff chances spread.
export function simulateMany(inputs, team, runs, rng = makeRng()) {
  const points = [];
  let playoffs = 0;
  for (let i = 0; i < runs; i++) {
    const { records, picture } = simulateSeason(inputs, rng);
    points.push(records[team].points);
    if (picture[team].seed) playoffs += 1;
  }
  points.sort((a, b) => a - b);
  const at = (q) => points[Math.min(points.length - 1, Math.floor(q * points.length))];
  return { runs, points, playoffPct: playoffs / runs, median: at(0.5), low: at(0.1), high: at(0.9) };
}

// The points the last playoff team in the team's conference finished with
// in a simulated season (for "missed by N points").
export function cutLine(result, team) {
  const conference = result.records[team].conference;
  const inTeams = Object.entries(result.picture)
    .filter(([abbrev, p]) => p.seed && result.records[abbrev].conference === conference)
    .map(([abbrev]) => result.records[abbrev].points);
  return Math.min(...inTeams);
}
