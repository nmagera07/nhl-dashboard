import { useEffect, useRef, useState } from "react";
import { formatOdds } from "../utils/playoffRace.js";

const HEIGHT = 260;
const PAD = { top: 12, right: 14, bottom: 24, left: 40 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Tracks the rendered width, so the SVG draws at real pixels and its text
// stays readable on phones (a scaled viewBox would shrink the labels).
function useWidth(ref, fallback = 720) {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width) || fallback));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, fallback]);
  return width;
}

function linePath(values, x, y) {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

function monthTicks(dates) {
  const ticks = [];
  let lastMonth = null;
  dates.forEach((iso, i) => {
    const month = Number(iso.slice(5, 7)) - 1;
    if (month !== lastMonth) ticks.push({ i, label: MONTHS[month] });
    lastMonth = month;
  });
  return ticks;
}

function shortDate(iso) {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;
}

// Playoff odds over the season, one line per team. Every line stays dim
// except the highlighted team; hovering shows that team's odds on a date,
// and tapping near a line highlights it.
function OddsChart({ dates, series, highlighted, onHighlight }) {
  const wrapRef = useRef(null);
  const width = useWidth(wrapRef);
  const [hoverIndex, setHoverIndex] = useState(null);

  const innerW = width - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i) => PAD.left + (dates.length > 1 ? (i / (dates.length - 1)) * innerW : innerW / 2);
  const y = (v) => PAD.top + (1 - v) * innerH;

  const indexAt = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * width;
    if (dates.length < 2) return 0;
    return Math.max(0, Math.min(dates.length - 1, Math.round(((px - PAD.left) / innerW) * (dates.length - 1))));
  };

  const handleClick = (event) => {
    const i = indexAt(event);
    const rect = event.currentTarget.getBoundingClientRect();
    const py = ((event.clientY - rect.top) / rect.height) * HEIGHT;
    let best = null;
    series.forEach((s) => {
      const v = s.values[i];
      if (v == null) return;
      const dist = Math.abs(y(v) - py);
      if (!best || dist < best.dist) best = { team: s.team, dist };
    });
    if (best && best.dist < 24) onHighlight(best.team === highlighted ? null : best.team);
  };

  const focus = series.find((s) => s.team === highlighted);
  const lastIndex = dates.length - 1;
  const readoutIndex = hoverIndex ?? lastIndex;
  const readout = focus?.values[readoutIndex];
  const ordered = focus ? [...series.filter((s) => s !== focus), focus] : series;

  return (
    <div className="odds-chart" ref={wrapRef}>
      <p className="odds-chart-readout" aria-live="polite">
        {focus ? (
          <>
            <strong>{focus.team}</strong> {formatOdds(readout)}
            <span> on {shortDate(dates[readoutIndex])}</span>
          </>
        ) : (
          <span>Tap a line or a team to follow its race</span>
        )}
      </p>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`Playoff odds from ${shortDate(dates[0])} to ${shortDate(dates[lastIndex])}`}
        onPointerMove={(e) => setHoverIndex(indexAt(e))}
        onPointerLeave={() => setHoverIndex(null)}
        onClick={handleClick}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line className={v === 0.5 ? "odds-grid odds-grid-mid" : "odds-grid"} x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
            <text className="odds-axis" x={PAD.left - 8} y={y(v) + 4} textAnchor="end">{v * 100}%</text>
          </g>
        ))}
        {monthTicks(dates).map(({ i, label }) => (
          <text key={`${label}-${i}`} className="odds-axis" x={x(i)} y={HEIGHT - 6} textAnchor="middle">{label}</text>
        ))}
        {hoverIndex != null && <line className="odds-hover" x1={x(hoverIndex)} x2={x(hoverIndex)} y1={PAD.top} y2={PAD.top + innerH} />}
        {ordered.map((s) => {
          const last = s.values[lastIndex];
          const tone = s === focus ? "odds-line odds-line-focus" : last != null && last >= 0.5 ? "odds-line odds-line-in" : "odds-line";
          return <path key={s.team} className={tone} d={linePath(s.values, x, y)} />;
        })}
        {focus && readout != null && <circle className="odds-dot" cx={x(readoutIndex)} cy={y(readout)} r="4.5" />}
      </svg>
    </div>
  );
}

export default OddsChart;
