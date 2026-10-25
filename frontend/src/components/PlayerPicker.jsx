import { useEffect, useState } from "react";
import { API_BASE } from "../config.js";

const MIN_CHARS = 3;
const DEBOUNCE_MS = 300;
const season = (id) => `${String(id).slice(0, 4)}-${String(id).slice(6)}`;

// Find any NHL player, current or retired (API /players/search), and pick one.
export default function PlayerPicker({ onPick, label = "Find a player", autoFocus = false }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null); // {q, players}: tied to the query they answer
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

  const found = results?.q === q ? results.players : null;
  return (
    <div className="player-picker">
      <input className="search-input" placeholder="Type a name: McDavid, Gretzky…" aria-label={label} value={query}
             onChange={(e) => setQuery(e.target.value)} autoFocus={autoFocus} />
      {found && found.length === 0 && <p className="player-picker-empty">No NHL players match "{q}".</p>}
      {found && found.length > 0 && (
        <ul>
          {found.map((p) => (
            <li key={p.player_id}>
              <button type="button" onClick={() => onPick(p.player_id)}>
                <strong>{p.name}</strong>
                <span>
                  {p.position_code} · {p.active ? p.last_team_abbrev || "Active" : `Retired, last played ${season(p.last_season_id)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
