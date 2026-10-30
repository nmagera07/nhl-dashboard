import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import GameCalendar from "../components/GameCalendar.jsx";
import Scoreboard from "../components/Scoreboard.jsx";
import MyTeamCard, { TeamPicker } from "../components/MyTeamCard.jsx";
import PickemCard from "../components/PickemCard.jsx";
import SwingOfTheNight from "../components/SwingOfTheNight.jsx";
import TopHeadlines from "../components/TopHeadlines.jsx";
import { useFollowedTeams } from "../hooks/useFavoriteTeam.js";
import { isValidISODate, longDateLabel, relativeDayLabel, shiftDate, todayISO } from "../utils/dates.js";

const UNDO_MS = 8000;

// The selected day lives in the URL (/?date=2026-10-06), so the back
// button, refreshes, and shared links all keep it. No date = today.
function ScoresPage({ standings = [], playoffOddsByTeam = {} }) {
  const [following, { follow, restore }] = useFollowedTeams();
  // "Stopped following PIT · Undo" for a few seconds after an unfollow on the card.
  const [undo, setUndo] = useState(null); // { team, before }
  useEffect(() => {
    if (!undo) return undefined;
    const timer = setTimeout(() => setUndo(null), UNDO_MS);
    return () => clearTimeout(timer);
  }, [undo]);
  const myTeams = following.map((abbrev) => standings.find((t) => t.team_abbrev === abbrev)).filter(Boolean);
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
      {/* Scores first: the games lead, with your team's game pinned to the top.
          Your team's card and the headlines follow; the morning digest lives on News. */}
      <p className="page-subtitle scores-date">{longDateLabel(date)}</p>
      <Scoreboard key={date} date={isToday ? null : date} pinTeams={following} />
      {isToday && <PickemCard />}
      {isToday && <SwingOfTheNight />}
      {myTeams.length > 0 ? (
        <MyTeamCard followed={myTeams} oddsByTeam={playoffOddsByTeam} teams={standings}
                    onUnfollow={(team, before) => setUndo({ team, before })} />
      ) : standings.length > 0 && following.length === 0 ? (
        <div className="my-team-prompt">
          <TeamPicker teams={standings} onPick={(abbrev) => abbrev && follow(abbrev)} />
          <span>Pin your team's next game, results, and playoff odds here.</span>
        </div>
      ) : null}
      {undo && (
        <p className="my-team-undo" role="status">
          Stopped following {undo.team} ·{" "}
          <button type="button" className="link-button" onClick={() => { restore(undo.before); setUndo(null); }}>Undo</button>
        </p>
      )}
      {isToday && <TopHeadlines />}
    </main>
  );
}

export default ScoresPage;
