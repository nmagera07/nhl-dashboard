import { goalClip } from "../utils/highlights.js";

const pct = (p) => `${Math.round(p * 100)}%`;
// Shown when someone arrives from a Swing of the Night link (?swing={date}):
// the moment in words, the goal's clip, and a jump to the chart, which rings
// it. swing is that night's /swing-of-the-night, already checked to be this game.
export default function SwingBanner({ swing: data, game, onShowChart }) {
  const { goal } = data;
  const clip = goalClip(game.summary?.scoring, goal.second);
  const label = new Date(`${data.date}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
  return (
    <section className="swing-banner" aria-label="Swing of the Night">
      <span className="swing-eyebrow">Swing of the Night · {label}</span>
      <strong>{goal.scorer || goal.team} {goal.effect} with {goal.when}</strong>
      <span className="swing-detail">{goal.team} went from {pct(goal.before)} to {pct(goal.after)} to win</span>
      <span className="swing-banner-actions">
        {clip && <a className="swing-banner-watch" href={clip} target="_blank" rel="noopener noreferrer">▶ Watch the goal</a>}
        <button type="button" onClick={onShowChart}>See it on the chart</button>
      </span>
    </section>
  );
}
