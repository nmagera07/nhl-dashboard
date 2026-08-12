import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API_BASE } from "../config.js";

const label = (team) => team?.abbrev || team?.placeName?.default || team?.name?.default || "Team";

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
    </main>
  );
}
