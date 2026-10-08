// Shared game-state helpers for the scoreboard cards.

const LIVE_STATES = new Set(["LIVE", "CRIT"]);
const FINAL_STATES = new Set(["FINAL", "OFF"]);
const ordinal = (n) => ["1st", "2nd", "3rd"][n - 1] || `${n}th`;

export function phase(game) {
  if (LIVE_STATES.has(game.gameState)) return "live";
  if (FINAL_STATES.has(game.gameState)) return "final";
  return "upcoming";
}

function periodLabel(pd) {
  if (!pd) return "";
  if (pd.periodType === "SO") return "SO";
  if (pd.periodType === "OT") {
    const n = pd.number - (pd.maxRegulationPeriods || 3);
    return n > 1 ? `${n}OT` : "OT";
  }
  return ordinal(pd.number);
}

export function statusLabel(game) {
  const p = phase(game);
  if (p === "live") {
    const period = periodLabel(game.periodDescriptor);
    if (game.clock?.inIntermission) return `${period} Intermission`;
    return [period, game.clock?.timeRemaining].filter(Boolean).join(" · ") || "Live";
  }
  if (p === "final") {
    const last = game.gameOutcome?.lastPeriodType || game.periodDescriptor?.periodType;
    return last === "OT" || last === "SO" ? `Final/${last}` : "Final";
  }
  return game.startTimeUTC
    ? new Date(game.startTimeUTC).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "Scheduled";
}

// Live games first (that's why you opened the app), then upcoming by
// start time, then finals.
const PHASE_ORDER = { live: 0, upcoming: 1, final: 2 };
export function sortGames(games) {
  return [...games].sort(
    (a, b) =>
      PHASE_ORDER[phase(a)] - PHASE_ORDER[phase(b)] ||
      String(a.startTimeUTC).localeCompare(String(b.startTimeUTC))
  );
}
