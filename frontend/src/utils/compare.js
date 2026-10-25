// Player comparison: the rows the compare page shows for two players'
// /players/{id} data (current or retired), with which side is better.
import { formatSeasonLabel } from "./formatSeasonLabel.js";
import { formatSigned } from "./format.js";

const perGame = (total, games) => (total != null && games ? total / games : null);
const fixed = (digits) => (v) => (v == null ? "—" : Number(v).toFixed(digits));
const whole = (v) => (v == null ? "—" : String(v));
const signed = (v) => (v == null ? "—" : formatSigned(v, 0));
const savePct = (v) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

export const isGoalie = (player) => player?.position_code === "G";

// The regular season he scored the most points (skaters) or won the most games (goalies).
export function bestSeason(player) {
  const key = isGoalie(player) ? "wins" : "points";
  const seasons = (player?.season_history || []).filter((s) => s.season_type === "regular_season" && s[key] != null);
  return seasons.reduce((best, s) => (!best || s[key] > best[key] ? s : best), null);
}

// [{section, label, a, b, show, better}] where a/b are numbers (or null), show formats one, and better
// is "high" or "low" (null: not compared, like a season label).
export function compareRows(a, b) {
  const goalie = isGoalie(a);
  const rows = [];
  const add = (section, label, get, show, better = "high") => {
    const va = get(a) ?? null;
    const vb = get(b) ?? null;
    if (va == null && vb == null) return;
    rows.push({ section, label, a: va, b: vb, show, better });
  };
  const rs = (p) => p.career_totals?.regular_season || {};
  const po = (p) => p.career_totals?.playoffs || {};
  const best = { a: bestSeason(a), b: bestSeason(b) };
  const bestOf = (p) => (p === a ? best.a : best.b);
  const now = (p) => p.season_stats?.[0] || null;

  if (goalie) {
    add("Career", "Games", (p) => rs(p).games_played, whole);
    add("Career", "Wins", (p) => rs(p).wins, whole);
    add("Career", "Save %", (p) => rs(p).save_pctg, savePct);
    add("Career", "Goals against avg", (p) => rs(p).goals_against_avg, fixed(2), "low");
    add("Career", "Shutouts", (p) => rs(p).shutouts, whole);
    add("Playoffs", "Games", (p) => po(p).games_played, whole);
    add("Playoffs", "Wins", (p) => po(p).wins, whole);
    add("Playoffs", "Save %", (p) => po(p).save_pctg, savePct);
    add("Best season", "Season", (p) => bestOf(p)?.season_id, formatSeasonLabel, null);
    add("Best season", "Wins", (p) => bestOf(p)?.wins, whole);
    add("Best season", "Save %", (p) => bestOf(p)?.save_pctg, savePct);
  } else {
    add("Career", "Games", (p) => rs(p).games_played, whole);
    add("Career", "Goals", (p) => rs(p).goals, whole);
    add("Career", "Assists", (p) => rs(p).assists, whole);
    add("Career", "Points", (p) => rs(p).points, whole);
    add("Career", "Points per game", (p) => perGame(rs(p).points, rs(p).games_played), fixed(2));
    add("Career", "Goals per game", (p) => perGame(rs(p).goals, rs(p).games_played), fixed(2));
    add("Career", "+/-", (p) => rs(p).plus_minus, signed);
    add("Playoffs", "Games", (p) => po(p).games_played, whole);
    add("Playoffs", "Points", (p) => po(p).points, whole);
    add("Playoffs", "Points per game", (p) => perGame(po(p).points, po(p).games_played), fixed(2));
    add("Best season", "Season", (p) => bestOf(p)?.season_id, formatSeasonLabel, null);
    add("Best season", "Points", (p) => bestOf(p)?.points, whole);
    add("Best season", "Goals", (p) => bestOf(p)?.goals, whole);
  }
  if (now(a) || now(b)) {
    add("This season", "Games", (p) => now(p)?.games_played, whole, null);
    add("This season", goalie ? "Wins" : "Points", (p) => now(p)?.[goalie ? "wins" : "points"], whole);
    add("This season", "WAR", (p) => p.war?.war, (v) => (v == null ? "—" : formatSigned(v, 2)));
  }
  return rows;
}

// "a", "b", or null (a tie, a missing side, or a row that isn't compared).
export function winner(row) {
  if (!row.better || row.a == null || row.b == null || row.a === row.b) return null;
  const aWins = row.better === "high" ? row.a > row.b : row.a < row.b;
  return aWins ? "a" : "b";
}
