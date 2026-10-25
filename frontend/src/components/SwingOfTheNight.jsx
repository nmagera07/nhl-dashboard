import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import ShareButton from "./ShareButton.jsx";

const pct = (p) => `${Math.round(p * 100)}%`;
const REGULATION = 3600;

// A tiny version of the game's win probability line (the home team's
// chance, top = home), with the moment marked.
function Sparkline({ points, goal }) {
  const W = 120;
  const H = 40;
  const end = Math.max(REGULATION, points[points.length - 1][0]);
  const x = (s) => (s / end) * W;
  const y = (p) => 2 + (1 - p) * (H - 4);
  const d = points.map(([s, p], i) => `${i ? "L" : "M"}${x(s).toFixed(1)},${y(p).toFixed(1)}`).join("");
  const homeAfter = goal.side === "home" ? goal.after : 1 - goal.after;
  return (
    <svg className="swing-spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="swing-spark-mid" />
      <path d={d} className="swing-spark-line" />
      <circle cx={x(goal.second)} cy={y(homeAfter)} r="4" className="swing-spark-dot" />
    </svg>
  );
}

// Last night's biggest win-probability swing from a goal that didn't end
// the game (backend api._swing_of_the_night), linking to the game, with a
// share link whose preview is the swing's own card. Hidden after a night
// without games.
export default function SwingOfTheNight() {
  const { data } = useFetchWithStatus(`${API_BASE}/swing-of-the-night`);
  if (!data?.available) return null;
  const { game, goal } = data;
  const day = new Date(`${data.date}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
  const final = `${game.away} ${game.away_score}, ${game.home} ${game.home_score}${game.last_period && game.last_period !== "REG" ? ` (${game.last_period})` : ""}`;
  const headline = `${goal.scorer || goal.team} ${goal.effect} with ${goal.when}`;
  return (
    <section className="swing-card" aria-label="Swing of the Night">
      <Link className="swing-main" to={`/games/${game.id}`}>
        <Sparkline points={data.points} goal={goal} />
        <span className="swing-text">
          <span className="swing-eyebrow">Swing of the Night <span className="nowrap">· {day}</span></span>
          <strong>{headline}</strong>
          <span className="swing-detail">{goal.team} {pct(goal.before)} → {pct(goal.after)} to win · Final {final}</span>
        </span>
      </Link>
      <ShareButton url={`https://puckpulse.io/s/${data.date}`} title={`Swing of the Night: ${headline}`}
                   image={`${API_BASE}/og/swing/${data.date}.png`}
                   event="share-swing" label="Share Swing of the Night" />
    </section>
  );
}
