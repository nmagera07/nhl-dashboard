import { formatOdds } from "../utils/playoffRace.js";
import { ordinal } from "../utils/ordinal.js";
import { formatSigned as signed } from "../utils/format.js";

// Below this many goals/game, a factor barely moves the rating.
const NEUTRAL = 0.03;


function Effect({ value }) {
  const title = `${signed(value, 2)} goals/game`;
  if (Math.abs(value) < NEUTRAL) return <span className="odds-why-effect" title={title}>– little effect</span>;
  return value > 0
    ? <span className="odds-why-effect race-change-up" title={title}>▲ pushes up</span>
    : <span className="odds-why-effect race-change-down" title={title}>▼ pulls down</span>;
}

// Worded by size, not rank: early on every schedule is within a hair of
// average, and "22nd easiest" alone would oversell the gap.
function scheduleWord(effect) {
  if (Math.abs(effect) < NEUTRAL) return "about average";
  return effect > 0 ? "easier than most" : "tougher than most";
}

// "Why these odds?": the team's rating split into what built it (this
// season's goals and xG, last season's carryover, roster moves since)
// plus its remaining schedule, each with which way it pushes. Opens under
// the selected row on the Playoffs page. `why` is one team from GET /playoff-odds/why.
function OddsWhy({ pct, why, teams, status }) {
  if (status === "error") return <p className="odds-why-note">Couldn't load the breakdown.</p>;
  if (!why) {
    return (
      <p className="odds-why-note">
        {status === "ready" ? "The breakdown arrives with the next morning update." : "Loading…"}
      </p>
    );
  }
  const games = `${why.games_played} game${why.games_played === 1 ? "" : "s"}`;
  const priorUnit = why.xg == null ? "goals" : "xG";
  const sched = why.schedule;

  return (
    <div className="odds-why">
      <p className="odds-why-title">
        <strong>Why {formatOdds(pct)}?</strong> Rated {ordinal(why.rating_rank)} of {teams} ({signed(why.rating, 2)} goals/game vs. an average team).
      </p>
      <dl className="odds-why-list">
        <div>
          <dt>Goals</dt>
          <dd>{signed(why.goal_diff, 0)} goal differential in {games}</dd>
          <dd><Effect value={why.goals} /></dd>
        </div>
        {why.xg != null && (
          <div>
            <dt>Expected goals</dt>
            <dd>{signed(why.xg_diff, 1)} xG differential (shot quality)</dd>
            <dd><Effect value={why.xg} /></dd>
          </div>
        )}
        <div>
          <dt>Last season</dt>
          <dd>
            {signed(why.last_season_per_game, 2)} {priorUnit}/game. Still {Math.round(why.last_season_share * 100)}% of the rating; it fades as games are played
          </dd>
          <dd><Effect value={why.last_season} /></dd>
        </div>
        {Math.abs(why.roster_change_per_game ?? 0) >= NEUTRAL && (
          <div>
            <dt>Roster moves</dt>
            <dd>{signed(why.roster_change_per_game, 2)} goals/game from players gained and lost since last season</dd>
            <dd><Effect value={why.roster} /></dd>
          </div>
        )}
        {sched.games_left > 0 && (
          <div>
            <dt>Schedule</dt>
            <dd>{sched.games_left} games left, {scheduleWord(sched.effect)} ({ordinal(sched.rank)} easiest of {teams})</dd>
            <dd><Effect value={sched.effect} /></dd>
          </div>
        )}
      </dl>
      <p className="odds-why-note">The points already in the bank count too: the simulation starts from today's standings.</p>
    </div>
  );
}

export default OddsWhy;
