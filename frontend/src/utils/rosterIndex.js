// "Matthew Knies" -> "Knies", "Luca Del Bel Belluz" -> "Del Bel Belluz".
export const lastName = (name) => name.split(" ").slice(1).join(" ") || name;
const plain = (s) => (s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");

// The team's roster, looked up by player id or by name (NHL.com's lineups
// give names only): full name first, then a last name only one player has.
export function rosterIndex(roster) {
  const players = Array.isArray(roster) ? roster : [];
  const byId = new Map(players.map((p) => [p.player_id, p]));
  const byName = new Map(players.map((p) => [plain(`${p.first_name} ${p.last_name}`), p]));
  const byLast = new Map();
  for (const p of players) {
    const key = plain(p.last_name);
    byLast.set(key, byLast.has(key) ? null : p);
  }
  return {
    byId: (id) => byId.get(id) || null,
    byName: (name) => byName.get(plain(name)) || byLast.get(plain(lastName(name))) || null,
  };
}
