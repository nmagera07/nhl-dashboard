import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import GameCalendar from "../components/GameCalendar.jsx";
import Scoreboard from "../components/Scoreboard.jsx";
import MyTeamCard, { TeamPicker } from "../components/MyTeamCard.jsx";
import { useFavoriteTeam } from "../hooks/useFavoriteTeam.js";
import { isValidISODate, longDateLabel, relativeDayLabel, shiftDate, todayISO } from "../utils/dates.js";

// The selected day lives in the URL (/?date=2026-10-06), so the back
// button, refreshes, and shared links all keep it. No date = today.
function ScoresPage({ standings = [], playoffOddsByTeam = {} }) {
  const [favorite, setFavorite] = useFavoriteTeam();
  const myTeam = standings.find((t) => t.team_abbrev === favorite);
  const [searchParams, setSearchParams] = useSearchParams();
  const today = todayISO();
  const param = searchParams.get("date");
  const date = isValidISODate(param) ? param : today;
  const isToday = date === today;
  const [calendarOpen, setCalendarOpen] = useState(false);
  const closeCalendar = useCallback(() => setCalendarOpen(false), []);

  const goTo = (next) => {
    setSearchParams(next === today ? {} : { date: next });
    setCalendarOpen(false);
  };

  return (
    <main className="page">
      <div className="page-header scores-header">
        <h1>Scores</h1>
        <div className="date-bar" role="group" aria-label="Choose a day">
          <button type="button" className="date-bar-step" onClick={() => goTo(shiftDate(date, -1))} aria-label="Previous day">‹</button>
          <div className="date-bar-picker-wrap">
            <button
              type="button"
              className="date-bar-picker"
              aria-haspopup="dialog"
              aria-expanded={calendarOpen}
              aria-label={`${relativeDayLabel(date, today)}, open calendar`}
              onClick={() => setCalendarOpen((open) => !open)}
            >
              {relativeDayLabel(date, today)}
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
            </button>
            {calendarOpen && (
              <GameCalendar value={date} today={today} onSelect={goTo} onClose={closeCalendar} />
            )}
          </div>
          <button type="button" className="date-bar-step" onClick={() => goTo(shiftDate(date, 1))} aria-label="Next day">›</button>
          {!isToday && (
            <button type="button" className="date-bar-today" onClick={() => goTo(today)}>Today</button>
          )}
        </div>
      </div>
      {myTeam ? (
        <MyTeamCard team={myTeam} odds={playoffOddsByTeam[myTeam.team_abbrev]} teams={standings} onChangeTeam={setFavorite} />
      ) : standings.length > 0 && !favorite ? (
        <div className="my-team-prompt">
          <TeamPicker teams={standings} onPick={setFavorite} />
          <span>Pin your team's next game, results, and playoff odds here.</span>
        </div>
      ) : null}
      <p className="page-subtitle scores-date">{longDateLabel(date)}</p>
      <Scoreboard key={date} date={isToday ? null : date} />
    </main>
  );
}

export default ScoresPage;
