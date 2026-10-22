// "Beat PuckPulse" pick'em: the player's key (kept in this browser, shown
// as a recovery code) and the API calls. Keys only travel in POST bodies.
import { API_BASE } from "../config.js";

const KEY = "puckpulse:pickem-key";

export function savedKey() {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked: they can still paste their recovery code each visit
  }
}

export function saveKey(key) {
  try {
    if (key) window.localStorage.setItem(KEY, key);
    else window.localStorage.removeItem(KEY);
  } catch {
    // nothing to do
  }
}

async function post(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Something went wrong. Try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

export const joinPickem = (name) => post("/pickem/join", { name });
export const fetchMe = (key, date) => post("/pickem/me", date ? { key, date } : { key });
export const makePick = (key, gameId, team) => post("/pickem/pick", { key, game_id: gameId, team });

const NOT_STARTED = new Set(["FUT", "PRE"]);

// A pick'em game: a regular-season or playoff game. Picks lock at puck drop.
export const pickable = (game) => game?.gameType === 2 || game?.gameType === 3;
export const pickOpen = (game, now = Date.now()) =>
  pickable(game) && NOT_STARTED.has(game.gameState) && now < new Date(game.startTimeUTC).getTime();

export const ordinal = (n) => {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
};

export function record(correct, graded) {
  if (!graded) return "No results yet";
  return `${correct}-${graded - correct} (${Math.round((100 * correct) / graded)}%)`;
}
