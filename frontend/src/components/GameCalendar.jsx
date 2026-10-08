import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../config.js";
import { longDateLabel, monthGrid, monthLabel, monthOf, shiftMonth } from "../utils/dates.js";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

// Month calendar for the Scores page. Only days with games in the current
// season are selectable; month navigation stops at the season's edges.
// Data comes from GET /games/calendar/{YYYY-MM} (cached per month here).
function GameCalendar({ value, today, onSelect, onClose }) {
  const [month, setMonth] = useState(monthOf(value));
  const [months, setMonths] = useState({}); // "YYYY-MM" -> calendar response
  const [failedMonth, setFailedMonth] = useState(null); // month whose fetch failed
  const ref = useRef(null);

  useEffect(() => {
    if (months[month]) return undefined;
    let active = true;
    fetch(`${API_BASE}/games/calendar/${month}`)
      .then((response) => {
        if (!response.ok) throw new Error("calendar unavailable");
        return response.json();
      })
      .then((data) => active && setMonths((prev) => ({ ...prev, [month]: data })))
      .catch(() => active && setFailedMonth(month));
    return () => { active = false; };
  }, [month, months]);

  // Close on Escape or a click outside the calendar.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    const onPointer = (e) => ref.current && !ref.current.contains(e.target) && onClose();
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [onClose]);

  const data = months[month];
  const error = failedMonth === month && !data;
  // Season bounds from any month loaded so far (they're the same season).
  const season = data || Object.values(months)[0];
  const canGoBack = !season?.season_start || month > monthOf(season.season_start);
  const canGoForward = !season?.season_end || month < monthOf(season.season_end);
  const gamesOn = Object.fromEntries((data?.days || []).map((d) => [d.date, d.games]));

  return (
    <div className="game-calendar" ref={ref} role="dialog" aria-label="Pick a game day">
      <div className="game-calendar-header">
        <button type="button" onClick={() => setMonth(shiftMonth(month, -1))} disabled={!canGoBack} aria-label="Previous month">‹</button>
        <strong>{monthLabel(month)}</strong>
        <button type="button" onClick={() => setMonth(shiftMonth(month, 1))} disabled={!canGoForward} aria-label="Next month">›</button>
      </div>
      <div className="game-calendar-grid">
        {WEEKDAYS.map((d, i) => <span key={i} className="game-calendar-weekday" aria-hidden="true">{d}</span>)}
        {monthGrid(month).map((iso, i) => {
          if (!iso) return <span key={`blank-${i}`} />;
          const games = gamesOn[iso];
          const classes = [
            "game-calendar-day",
            iso === value && "is-selected",
            iso === today && "is-today",
          ].filter(Boolean).join(" ");
          return (
            <button
              key={iso}
              type="button"
              className={classes}
              disabled={!games}
              aria-label={`${longDateLabel(iso)}${games ? `, ${games} game${games === 1 ? "" : "s"}` : ", no games"}`}
              aria-pressed={iso === value}
              onClick={() => onSelect(iso)}
            >
              <span>{Number(iso.slice(8))}</span>
              {games ? <small>{games}</small> : null}
            </button>
          );
        })}
      </div>
      <p className="game-calendar-note">
        {error ? "Couldn't load game days." : !data ? "Loading game days…" : data.days.length === 0 ? "No games this month." : "Numbers show games that day."}
      </p>
    </div>
  );
}

export default GameCalendar;
