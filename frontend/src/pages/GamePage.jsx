import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API_BASE } from "../config.js";

const label = (team) => team?.abbrev || team?.placeName?.default || team?.name?.default || "Team";
const statLabel = (value) => value?.displayName || value?.category || "Stat";

export default function GamePage() {
  const { gameId } = useParams();
  const [game, setGame] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/games/${gameId}/boxscore`)
      .then((response) => response.ok ? response.json() : response.json().then((body) => Promise.reject(new Error(body.detail))))
      .then(setGame)
      .catch((requestError) => setError(requestError.message || "Could not load this box score."));
  }, [gameId]);

  if (error) return <div className="page-message status-error">{error}</div>;
  if (!game) return <div className="page-message">Loading box score…</div>;

  const away = game.awayTeam;
  const home = game.homeTeam;
  const summary = game.summary?.scoring || [];
  const teamStats = game.teamGameStats || [];
  const playerStats = game.playerByGameStats || {};
  const skaters = [
    ...(playerStats.awayTeam?.forwards || []),
    ...(playerStats.awayTeam?.defense || []),
    ...(playerStats.homeTeam?.forwards || []),
    ...(playerStats.homeTeam?.defense || []),
  ];
  return (
    <main className="game-page">
      <Link className="back-link" to="/">← Back to dashboard</Link>
      <div className="game-hero">
        <span>{game.gameState === "FINAL" ? "FINAL" : game.gameState}</span>
        <h1>{label(away)} <strong>{away?.score ?? "—"}</strong> — <strong>{home?.score ?? "—"}</strong> {label(home)}</h1>
        <p>{game.gameDate}</p>
      </div>
      <section className="boxscore-card">
        <h2>Scoring summary</h2>
        {summary.length === 0 ? <p className="muted">Scoring details are not available yet.</p> : summary.map((period, index) => (
          <div className="scoring-period" key={`${period.periodDescriptor?.number || index}`}>
            <strong>{period.periodDescriptor?.displayName || `Period ${index + 1}`}</strong>
            {(period.goals || []).map((goal, goalIndex) => <p key={goal.eventId || goalIndex}>{goal.timeInPeriod} — {goal.name?.default || goal.scorer?.name?.default || "Goal"} ({goal.teamAbbrev || goal.team?.abbrev || "—"})</p>)}
          </div>
        ))}
      </section>
      {teamStats.length > 0 && (
        <section className="boxscore-card">
          <h2>Team stats</h2>
          <div className="game-stats-table">
            <div className="game-stats-row game-stats-header"><strong>{label(away)}</strong><span>Category</span><strong>{label(home)}</strong></div>
            {teamStats.map((stat) => <div className="game-stats-row" key={stat.category}><span>{stat.awayValue ?? "—"}</span><strong>{statLabel(stat)}</strong><span>{stat.homeValue ?? "—"}</span></div>)}
          </div>
        </section>
      )}
      {skaters.length > 0 && (
        <section className="boxscore-card">
          <h2>Player stats</h2>
          <div className="player-stats-list">
            {skaters.slice(0, 24).map((player) => <div className="player-stat-row" key={`${player.playerId}-${player.name?.default}`}><strong>{player.name?.default || "Player"}</strong><span>{player.goals ?? 0} G · {player.assists ?? 0} A · {player.points ?? 0} P</span></div>)}
          </div>
        </section>
      )}
    </main>
  );
}
