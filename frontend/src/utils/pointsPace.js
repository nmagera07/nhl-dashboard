// "Points pace" for the My Team card: how many points a team needs to reach
// the playoff line, the points % that takes over the games left, and a
// rough W-L-OTL record that gets there. Standard NHL points: W = 2, OTL = 1,
// L = 0. The season length (84 games from 2026-27) and each team's games
// left come from GET /playoff-line, never a hardcoded 82.

export const DEFAULT_SEASON_GAMES = 84;
export const LEAGUE_OTL_SHARE = 0.11; // ~11% of games end as an OT/SO loss
export const EARLY_GP = 10;

const CLINCHED = new Set(["x", "y", "z", "p"]);

// The smallest record over `gr` games worth at least `need` points, with
// about `share` of the games as OT losses.
export function neededRecord(need, gr, share) {
  if (need <= 0) return { w: 0, l: gr, otl: 0 };
  if (need > 2 * gr) return null;
  let otl = Math.min(Math.round(gr * share), need, gr);
  let w = Math.max(0, Math.ceil((need - otl) / 2));
  if (w + otl > gr) {
    // Not enough games for that many OT losses: turn some into wins.
    w = need - gr;
    otl = gr - w;
  }
  // Drop a spare OT loss if the wins alone already got there.
  while (otl > 0 && 2 * w + otl - 1 >= need) otl -= 1;
  return { w, l: gr - w - otl, otl };
}

/**
 * line: {p25, p50, p75} in points. team: {gp, pts, otl, games_left, clinch_indicator}.
 * seasonGames: the regular-season length from the API (84 from 2026-27).
 * Returns null when there's nothing to show (no line, season over).
 */
export function pointsPace(line, team, seasonGames = DEFAULT_SEASON_GAMES) {
  if (!line || line.p50 == null || !team) return null;
  const gp = team.gp ?? 0;
  const gr = Math.max(0, team.games_left ?? seasonGames - gp);
  if (gr === 0) return null;

  const cutline = line.p50;
  const ptsNeeded = Math.max(0, Math.ceil(cutline - team.pts));
  const reqPct = ptsNeeded / (2 * gr);
  const pointPctg = gp > 0 ? team.pts / (2 * gp) : null;
  const pace = pointPctg == null ? null : Math.round(pointPctg * 2 * seasonGames);

  const code = (team.clinch_indicator || "").toLowerCase();
  let state = "chasing";
  if (CLINCHED.has(code)) state = "clinched";
  else if (code === "e" || reqPct > 1) state = "eliminated";
  else if (ptsNeeded <= 0) state = "above";

  const share = gp >= EARLY_GP && gp > 0 ? (team.otl ?? 0) / gp : LEAGUE_OTL_SHARE;
  const record = state === "chasing" ? neededRecord(ptsNeeded, gr, share) : null;

  return {
    state,
    early: gp < EARLY_GP,
    cutline,
    low: line.p25,
    high: line.p75,
    pts: team.pts,
    gp,
    gamesRemaining: gr,
    ptsNeeded,
    reqPct,
    pointPctg,
    pace,
    record,
  };
}

// .586 style, like NHL points percentages.
export function formatPct(p) {
  if (p == null) return "—";
  return p >= 1 ? "1.000" : p.toFixed(3).replace(/^0/, "");
}
