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

// A copy of `player` with every season rescaled to the reference season's
// scoring (API /era/scoring): goals and assists times reference / that
// season's goals per team-game, rounded per season, and career totals
// rebuilt from the adjusted seasons. +/- isn't adjusted (it's left out).
// Goalies aren't adjusted here.
export function eraAdjust(player, era) {
  if (!player || !era || isGoalie(player)) return player;
  const factor = (seasonId) => {
    const scoring = era.seasons?.[String(seasonId)];
    return scoring ? era.reference / scoring : 1;
  };
  const adjust = (row) => {
    const f = factor(row.season_id);
    const goals = row.goals == null ? null : Math.round(row.goals * f);
    const assists = row.assists == null ? null : Math.round(row.assists * f);
    return { ...row, goals, assists, points: goals == null || assists == null ? null : goals + assists, plus_minus: null };
  };
  const history = (player.season_history || []).map(adjust);
  const total = (type) => {
    const rows = history.filter((s) => s.season_type === type);
    if (!rows.length) return null;
    const sum = (key) => rows.reduce((t, s) => t + (s[key] || 0), 0);
    return { games_played: sum("games_played"), goals: sum("goals"), assists: sum("assists"), points: sum("points") };
  };
  const current = player.season_stats?.[0];
  return {
    ...player,
    season_history: history,
    career_totals: { regular_season: total("regular_season"), playoffs: total("playoffs") },
    season_stats: current ? [adjust({ ...current, season_id: current.season_id })] : [],
  };
}
