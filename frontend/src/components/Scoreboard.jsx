import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE, GAME_PREVIEW_ID, SHOW_GAME_PREVIEW } from "../config.js";

function teamLabel(team) {
  return team?.abbrev || team?.placeName?.default || team?.name?.default || "—";
}

function gameLabel(game) {
  if (game.gameState === "LIVE" || game.gameState === "CRIT") return game.periodDescriptor?.periodType === "OT" ? "OT" : "LIVE";
  if (["FINAL", "OFF"].includes(game.gameState)) return "FINAL";
  return game.startTimeUTC
    ? new Date(game.startTimeUTC).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "SCHEDULED";
}

export default function Scoreboard() {
  const navigate = useNavigate();
  const [games, setGames] = useState([]);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let active = true;
    const load = () => fetch(`${API_BASE}/games/today`)
      .then((response) => {
        if (!response.ok) throw new Error("scoreboard unavailable");
        return response.json();
      })
      .then((data) => {
        if (!active) return;
        setGames(Array.isArray(data.games) ? data.games : []);
        setStatus("ready");
      })
      .catch(() => active && setStatus("error"));
    load();
    const timer = window.setInterval(load, 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return (
    <section className="scoreboard" aria-label="Today's NHL scoreboard">
      <div className="scoreboard-header"><strong>Scoreboard</strong><span>{status === "error" ? "Unavailable" : "Today"}</span></div>
      <div className="scoreboard-games">
        {status === "loading" && <span className="scoreboard-empty">Loading games…</span>}
        {status === "ready" && games.length === 0 && <span className="scoreboard-empty">No games scheduled today.</span>}
        {games.map((game) => (
          <button className="scoreboard-game" key={game.id} type="button" onClick={() => navigate(`/games/${game.id}`)}>
            <span className="scoreboard-status">{gameLabel(game)}</span>
            <span className="scoreboard-team"><span>{teamLabel(game.awayTeam)}</span><strong>{game.awayTeam?.score ?? "—"}</strong></span>
            <span className="scoreboard-team"><span>{teamLabel(game.homeTeam)}</span><strong>{game.homeTeam?.score ?? "—"}</strong></span>
          </button>
        ))}
        {SHOW_GAME_PREVIEW && (
          <button className="scoreboard-game scoreboard-preview" type="button" onClick={() => navigate(`/games/${GAME_PREVIEW_ID}`)}>
            <span className="scoreboard-status">Preview</span>
            <span className="scoreboard-team"><span>Historical game</span><strong>›</strong></span>
            <span className="scoreboard-team"><span>Open box score</span><strong>↗</strong></span>
          </button>
        )}
      </div>
    </section>
  );
}
