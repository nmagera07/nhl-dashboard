import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchMe, makePick, pickOpen, savedKey } from "../utils/pickem.js";
import { track } from "../utils/analytics.js";

const startTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// "Beat PuckPulse" from a game page: pick this game before puck drop. Without
// a pick'em name yet, a link to join instead.
export default function GamePick({ game }) {
  const key = savedKey();
  const [pick, setPick] = useState(null);
  const [error, setError] = useState(null);
  const gameId = game.id;
  const day = game.gameDate;

  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    fetchMe(key, day).then((m) => !cancelled && setPick(m.picks?.[String(gameId)] || null)).catch(() => {});
    return () => { cancelled = true; };
  }, [key, day, gameId]);

  if (!pickOpen(game)) return null;
  const away = game.awayTeam?.abbrev;
  const home = game.homeTeam?.abbrev;

  if (!key) {
    return (
      <Link className="pickem-link game-pick-join" to="/pickem">
        <span><strong>Beat PuckPulse</strong> · pick {away} or {home} before puck drop</span>
        <span aria-hidden="true">›</span>
      </Link>
    );
  }

  const choose = async (team) => {
    const before = pick;
    setError(null);
    setPick(team);
    try {
      await makePick(key, gameId, team);
      track("pickem-pick");
    } catch (err) {
      setPick(before);
      setError(err.message);
    }
  };

  return (
    <section className="boxscore-card game-pick" aria-label="Your pick">
      <div className="game-pick-row">
        <span className="game-pick-label">Your pick</span>
        {[away, home].map((team) => (
          <button key={team} type="button" className={`pickem-team${pick === team ? " pickem-team-picked" : ""}`}
                  aria-pressed={pick === team} onClick={() => choose(team)}>
            {team}
          </button>
        ))}
      </div>
      <p className="pickem-hint">
        Locks at {startTime(game.startTimeUTC)} · <Link className="accent-link" to="/pickem">Beat PuckPulse leaderboard</Link>
      </p>
      {error && <p className="pickem-error" role="alert">{error}</p>}
    </section>
  );
}
