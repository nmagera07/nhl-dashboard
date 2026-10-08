import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE, GAME_PREVIEW_ID, SHOW_GAME_PREVIEW } from "../config.js";
import { phase, sortGames, statusLabel } from "./gameStatus.js";
import { darkLogo } from "../utils/darkLogo.js";

function networks(game) {
  const names = (game.tvBroadcasts || []).filter((b) => b.market === "N").map((b) => b.network);
  return [...new Set(names)].slice(0, 2).join(", ");
}

function TeamLine({ team, phase: gamePhase, isWinner, isLoser }) {
  const showScore = gamePhase !== "upcoming";
  return (
    <span className={`game-card-team${isWinner ? " is-winner" : ""}${isLoser ? " is-loser" : ""}`}>
      {team?.logo ? <img className="game-card-logo" src={darkLogo(team.logo)} alt="" /> : <span className="game-card-logo" />}
      <span className="game-card-abbrev">{team?.abbrev || "—"}</span>
      {gamePhase === "upcoming" && team?.record && <span className="game-card-record">{team.record}</span>}
      {showScore && <strong className="game-card-score">{team?.score ?? 0}</strong>}
    </span>
  );
}

function GameCard({ game, onOpen }) {
  const p = phase(game);
  const away = game.awayTeam;
  const home = game.homeTeam;
  const decided = p === "final" && away?.score != null && home?.score != null && away.score !== home.score;
  const awayWon = decided && away.score > home.score;
  const tv = p === "upcoming" ? networks(game) : "";

  return (
    <button
      className={`scoreboard-game game-card-${p}`}
      type="button"
      onClick={onOpen}
      aria-label={`${away?.abbrev} at ${home?.abbrev}, ${statusLabel(game)}`}
    >
      <span className="game-card-status">
        {p === "live" && <span className="live-dot" />}
        {statusLabel(game)}
        {tv && <span className="game-card-tv">{tv}</span>}
      </span>
      <TeamLine team={away} phase={p} isWinner={decided && awayWon} isLoser={decided && !awayWon} />
      <TeamLine team={home} phase={p} isWinner={decided && !awayWon} isLoser={decided && awayWon} />
    </button>
  );
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
      {status === "loading" && <p className="scoreboard-empty">Loading games…</p>}
      {status === "error" && <p className="scoreboard-empty status-error">Scores are unavailable right now.</p>}
      {status === "ready" && games.length === 0 && <p className="scoreboard-empty">No games scheduled today.</p>}
      <div className="scoreboard-games">
        {sortGames(games).map((game) => (
          <GameCard key={game.id} game={game} onOpen={() => navigate(`/games/${game.id}`)} />
        ))}
        {SHOW_GAME_PREVIEW && (
          <button className="scoreboard-game scoreboard-preview" type="button" onClick={() => navigate(`/games/${GAME_PREVIEW_ID}`)}>
            <span className="game-card-status">Dev preview</span>
            <span className="game-card-team"><span className="game-card-abbrev">Historical game</span><strong className="game-card-score">↗</strong></span>
          </button>
        )}
      </div>
    </section>
  );
}
