// "My bets": bets the viewer tracks from the Bets tab, kept in this browser
// (no account, like followed teams). Each bet is 1 unit at the price shown
// when it was tapped, graded from the final score, with its closing-line
// value (CLV): the expected return of that price by the books' closing odds
// (margin removed). Beating the close is the honest test of a bet, win or lose.
import { formatSpread } from "./odds.js";

const KEY = "puckpulse:my-bets";
const FINAL = new Set(["OFF", "FINAL"]);

export function loadBets() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(KEY));
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function saveBets(bets) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(bets));
  } catch {
    // storage blocked or full: the bets last until the page closes
  }
}

export const betId = (gameId, market, side) => `${gameId}:${market}:${side}`;

// The bet as the Bets tab shows it: "PIT", "PIT −1.5", "Over 6.5".
export function betLabel(bet) {
  if (bet.market === "total") return `${bet.side === "over" ? "Over" : "Under"} ${bet.line}`;
  const team = bet.side === "home" ? bet.home : bet.away;
  return bet.market === "puck_line" ? `${team} ${formatSpread(bet.line)}` : team;
}

// The line a side was offered at: the spread from that side's view, or the total.
export function sideLine(board, market, side) {
  if (market === "puck_line") return side === "home" ? board.puck_line.home_spread : -board.puck_line.home_spread;
  if (market === "total") return board.total.line;
  return null;
}

export const decimalOdds = (price) => 1 + (price > 0 ? price / 100 : 100 / -price);

// {outcome: "win"|"loss"|"push", units, clv, closePrice} once the game is final, else null.
export function grade(bet, game, board) {
  if (!game || !FINAL.has(game.gameState)) return null;
  const away = game.awayTeam.score;
  const home = game.homeTeam.score;
  let margin;
  if (bet.market === "total") margin = bet.side === "over" ? away + home - bet.line : bet.line - away - home;
  else margin = (bet.side === "home" ? home - away : away - home) + (bet.line ?? 0);
  const outcome = margin > 0 ? "win" : margin < 0 ? "loss" : "push";
  const units = outcome === "win" ? decimalOdds(bet.price) - 1 : outcome === "loss" ? -1 : 0;
  // CLV only against the real close, and only at the same line (a total can move from 6.5 to 6).
  const close = board?.snapshot === "close" ? board[bet.market]?.[bet.side] : null;
  const sameLine = close && (bet.market === "moneyline" || sideLine(board, bet.market, bet.side) === bet.line);
  const clv = sameLine && close.market != null ? round(close.market * decimalOdds(bet.price) - 1) : null;
  return { outcome, units: round(units), clv, closePrice: sameLine ? close.price ?? null : null };
}

const round = (x) => Math.round(x * 10000) / 10000;

// Record, units, return per bet, and the average CLV over the graded bets.
export function summarize(bets) {
  const graded = bets.filter((b) => b.result);
  const count = (outcome) => graded.filter((b) => b.result.outcome === outcome).length;
  const units = graded.reduce((sum, b) => sum + b.result.units, 0);
  const withClv = graded.filter((b) => b.result.clv != null);
  return {
    wins: count("win"), losses: count("loss"), pushes: count("push"), graded: graded.length,
    units: round(units),
    roi: graded.length ? round(units / graded.length) : null,
    clv: withClv.length ? round(withClv.reduce((sum, b) => sum + b.result.clv, 0) / withClv.length) : null,
    beatClose: withClv.filter((b) => b.result.clv > 0).length,
    clvCount: withClv.length,
  };
}
