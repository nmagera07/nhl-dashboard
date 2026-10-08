import { useSearchParams } from "react-router-dom";
import Scoreboard from "../components/Scoreboard.jsx";
import { isValidISODate, longDateLabel, relativeDayLabel, shiftDate, todayISO } from "../utils/dates.js";

// The selected day lives in the URL (/?date=2026-10-06), so the back
// button, refreshes, and shared links all keep it. No date = today.
function ScoresPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const today = todayISO();
  const param = searchParams.get("date");
  const date = isValidISODate(param) ? param : today;
  const isToday = date === today;

  const goTo = (next) => {
    setSearchParams(next === today ? {} : { date: next });
  };

  return (
    <main className="page">
      <div className="page-header scores-header">
        <h1>Scores</h1>
        <div className="date-bar" role="group" aria-label="Choose a day">
          <button type="button" className="date-bar-step" onClick={() => goTo(shiftDate(date, -1))} aria-label="Previous day">‹</button>
          <label className="date-bar-picker">
            <span className="date-bar-label">{relativeDayLabel(date, today)}</span>
            <input
              type="date"
              value={date}
              aria-label="Pick a date"
              onChange={(e) => isValidISODate(e.target.value) && goTo(e.target.value)}
            />
          </label>
          <button type="button" className="date-bar-step" onClick={() => goTo(shiftDate(date, 1))} aria-label="Next day">›</button>
          {!isToday && (
            <button type="button" className="date-bar-today" onClick={() => goTo(today)}>Today</button>
          )}
        </div>
      </div>
      <p className="page-subtitle scores-date">{longDateLabel(date)}</p>
      <Scoreboard key={date} date={isToday ? null : date} />
    </main>
  );
}

export default ScoresPage;
