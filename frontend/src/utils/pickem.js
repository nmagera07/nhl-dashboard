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

export function record(correct, graded) {
  if (!graded) return "No results yet";
  return `${correct}-${graded - correct} (${Math.round((100 * correct) / graded)}%)`;
}
