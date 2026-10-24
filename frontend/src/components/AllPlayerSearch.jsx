import { useEffect, useState } from "react";
import { API_BASE } from "../config.js";

const MIN_CHARS = 3;
const DEBOUNCE_MS = 300;
const season = (id) => `${String(id).slice(0, 4)}-${String(id).slice(6)}`;

// Under the Players search: everyone else who has played in the NHL and
// matches (retired players, and anyone not on a current roster), from the
// NHL's own player search (API /players/search). Players already in the
// list above are left out.
export default function AllPlayerSearch({ query, exclude, onSelectPlayer }) {
  // {q, players}: results stay tied to the query they answer, so a stale
  // answer never shows under a newer query.
  const [results, setResults] = useState(null);
  const q = query.trim();

  useEffect(() => {
    if (q.length < MIN_CHARS) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/players/search?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((r) => (r.ok ? r.json() : { players: [] }))
        .then((body) => setResults({ q, players: body.players || [] }))
        .catch(() => {});
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  const others = results?.q === q ? results.players.filter((p) => !exclude.has(p.player_id)) : [];
  if (q.length < MIN_CHARS || others.length === 0) return null;
  return (
    <section className="all-players" aria-label="More players, including retired">
      <h2>More players, including retired</h2>
      <ul>
        {others.map((p) => (
          <li key={p.player_id}>
            <button type="button" onClick={() => onSelectPlayer(p.player_id)}>
              <strong>{p.name}</strong>
              <span>
                {p.position_code} · {p.active ? "Not on an NHL roster" : "Retired"} · last played {season(p.last_season_id)}
                {p.last_team_abbrev ? ` (${p.last_team_abbrev})` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
