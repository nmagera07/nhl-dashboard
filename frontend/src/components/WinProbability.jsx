import { useEffect, useState } from "react";
import { API_BASE } from "../config.js";

const HEIGHT = 200;
const PAD = { top: 14, right: 12, bottom: 22, left: 40 };
const REGULATION = 3600;

// Tracks the rendered width so the SVG draws at real pixels (see OddsChart).
// Takes the element, not a ref: the chart only mounts once its data arrives.
function useWidth(el, fallback = 720) {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width) || fallback));
    observer.observe(el);
    return () => observer.disconnect();
  }, [el, fallback]);
  return width;
}

const pct = (p) => `${Math.round(p * 100)}%`;

// "2nd 12:30" (time elapsed in the period, like the play-by-play), or "OT 1:45".
function gameClock(second, playoff) {
  const otLength = playoff ? 1200 : 300;
  const [label, start] = second < REGULATION
    ? [["1st", "2nd", "3rd"][Math.floor(second / 1200)], Math.floor(second / 1200) * 1200]
    : (() => {
      const n = Math.floor((second - REGULATION) / otLength);
      return [n ? `${n + 1}OT` : "OT", REGULATION + n * otLength];
    })();
  const into = second - start;
  return `${label} ${Math.floor(into / 60)}:${String(into % 60).padStart(2, "0")}`;
}

// Leader's side of the readout: "PIT 64%".
function favored(p, away, home) {
  return p >= 0.5 ? `${home} ${pct(p)}` : `${away} ${pct(1 - p)}`;
}

// The home team's chance to win through the game (backend win_probability.py),
// with a dot at each goal and the goal that swung it most called out. Hidden
// for games we didn't predict. `refreshKey` changes when the live box score
// refreshes, which refetches the curve.
export default function WinProbability({ gameId, away, home, playoff = false, refreshKey }) {
  const [wrap, setWrap] = useState(null);
  const width = useWidth(wrap);
  const [data, setData] = useState(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/games/${gameId}/win-probability`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => { if (!cancelled && body) setData(body); })
      .catch(() => {});  // keep the last curve; the chart is extra
    return () => { cancelled = true; };
  }, [gameId, refreshKey]);

  if (!data?.available || !data.points?.length) return null;

  const points = data.points;
  const end = Math.max(REGULATION, points[points.length - 1][0]);
  const innerW = width - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (s) => PAD.left + (s / end) * innerW;
  const y = (p) => PAD.top + (1 - p) * innerH;
  const line = points.map(([s, p], i) => `${i ? "L" : "M"}${x(s).toFixed(1)},${y(p).toFixed(1)}`).join("");
  const mid = y(0.5);
  const area = `${line}L${x(points[points.length - 1][0]).toFixed(1)},${mid}L${x(0)},${mid}Z`;
  const periods = [1200, 2400, ...(end > REGULATION ? [REGULATION] : [])];
  const labels = [["1st", 600], ["2nd", 1800], ["3rd", 3000], ...(end > REGULATION ? [["OT", (REGULATION + end) / 2]] : [])];

  const nearest = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const second = (((event.clientX - rect.left) / rect.width) * width - PAD.left) / innerW * end;
    let best = points[0];
    for (const pt of points) if (Math.abs(pt[0] - second) < Math.abs(best[0] - second)) best = pt;
    return best;
  };
  const [shownSecond, shownP] = hover || points[points.length - 1];
  const swing = data.swing;
  const swingTeam = swing && (swing.team === "home" ? home : away);
  const swingFor = (p) => (swing.team === "home" ? p : 1 - p);

  return (
    <section className="boxscore-card win-prob">
      <h2>Win probability</h2>
      <p className="win-prob-readout" aria-live="polite">
        <strong>{favored(shownP, away, home)}</strong>
        <span> · {hover ? gameClock(shownSecond, playoff) : "now"}</span>
      </p>
      <div className="win-prob-chart" ref={setWrap}>
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`${home} win probability through the game, from ${pct(points[0][1])} to ${pct(points[points.length - 1][1])}`}
          onPointerMove={(e) => setHover(nearest(e))}
          onPointerLeave={() => setHover(null)}
        >
          <defs>
            <clipPath id="wp-home"><rect x="0" y="0" width={width} height={mid} /></clipPath>
            <clipPath id="wp-away"><rect x="0" y={mid} width={width} height={HEIGHT - mid} /></clipPath>
          </defs>
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <line key={v} className={v === 0.5 ? "odds-grid odds-grid-mid" : "odds-grid"} x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
          ))}
          <text className="odds-axis win-prob-team" x={PAD.left - 8} y={y(1) + 10} textAnchor="end">{home}</text>
          <text className="odds-axis" x={PAD.left - 8} y={mid + 4} textAnchor="end">50%</text>
          <text className="odds-axis win-prob-team" x={PAD.left - 8} y={y(0) - 2} textAnchor="end">{away}</text>
          {periods.map((s) => <line key={s} className="odds-grid" x1={x(s)} x2={x(s)} y1={PAD.top} y2={PAD.top + innerH} />)}
          {labels.map(([label, s]) => <text key={label} className="odds-axis" x={x(s)} y={HEIGHT - 6} textAnchor="middle">{label}</text>)}
          <path className="win-prob-area win-prob-area-home" d={area} clipPath="url(#wp-home)" />
          <path className="win-prob-area win-prob-area-away" d={area} clipPath="url(#wp-away)" />
          <path className="win-prob-line" d={line} />
          {hover && <line className="odds-hover" x1={x(shownSecond)} x2={x(shownSecond)} y1={PAD.top} y2={PAD.top + innerH} />}
          {(data.goals || []).map((g) => (
            <circle key={`${g.second}-${g.team}-${g.after}`} className={`win-prob-goal win-prob-goal-${g.team}`} cx={x(g.second)} cy={y(g.after)} r={g.second === swing?.second && g.team === swing?.team ? 5.5 : 4}>
              <title>{`${g.scorer || (g.team === "home" ? home : away)} (${g.team === "home" ? home : away}), ${gameClock(g.second, playoff)}`}</title>
            </circle>
          ))}
        </svg>
      </div>
      {swing && (
        <p className="win-prob-swing">
          Biggest swing: <strong>{swing.scorer || swingTeam}</strong> ({swingTeam}), {gameClock(swing.second, playoff)} · {swingTeam}{" "}
          {pct(swingFor(swing.before))} → {pct(swingFor(swing.after))}
        </p>
      )}
    </section>
  );
}
