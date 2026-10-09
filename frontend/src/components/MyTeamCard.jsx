import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { darkLogo } from "../utils/darkLogo.js";
import { formatOdds } from "../utils/playoffRace.js";
import { gameTimeLabel } from "../utils/dates.js";

const LIVE_REFRESH_MS = 30_000;
function ordinal(n) {
  const suffixes = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0]);
}

const versus = (game) => `${game.home ? "vs" : "@"} ${game.opponent}`;

// Loads the team's schedule summary; refreshes every 30s while a game is live.
function useTeamSchedule(abbrev) {
  const [state, setState] = useState({ abbrev: null, data: null, error: false });

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const load = () =>
      fetch(`${API_BASE}/teams/${abbrev}/schedule`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.status))))
        .then((data) => {
          if (cancelled) return;
          setState({ abbrev, data, error: false });
          if (data.live) timer = setTimeout(load, LIVE_REFRESH_MS);
        })
        .catch(() => !cancelled && setState((s) => ({ ...s, abbrev, error: true })));
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [abbrev]);

  // Ignore a previous team's data while the new team's loads.
  return state.abbrev === abbrev ? state : { data: null, error: false };
}

function GameLine({ schedule }) {
  if (schedule.live) {
    const g = schedule.live;
    return (
      <Link className="my-team-game my-team-game-live" to={`/games/${g.id}`} aria-label={`Live: ${versus(g)}, ${g.team_score}–${g.opponent_score}`}>
        <span className="my-team-game-label"><span className="live-dot" aria-hidden="true" />Live</span>
        <span className="my-team-game-main">
          {versus(g)} <strong>{g.team_score}–{g.opponent_score}</strong>
        </span>
        <span className="my-team-game-cta">Watch ›</span>
      </Link>
    );
  }
  const next = schedule.upcoming[0];
  if (!next) return <p className="my-team-game my-team-game-none">No games scheduled.</p>;
  return (
    <Link className="my-team-game" to={`/games/${next.id}`} aria-label={`Next game: ${versus(next)}, ${gameTimeLabel(next.start_time_utc)}`}>
      <span className="my-team-game-label">Next</span>
      <span className="my-team-game-main">
        {next.opponent_logo && <img src={next.opponent_logo} alt="" />}
        {versus(next)}
      </span>
      <span className="my-team-game-time">{gameTimeLabel(next.start_time_utc)}</span>
    </Link>
  );
}

function RecentResults({ games }) {
  if (!games.length) return null;
  return (
    <div className="my-team-recent">
      <span className="my-team-game-label">Last {games.length}</span>
      <ol>
        {games.map((g) => (
          <li key={g.id}>
            <Link
              to={`/games/${g.id}`}
              className={`result-chip result-${g.result.toLowerCase()}`}
              title={`${g.result === "OTL" ? `Lost in ${g.last_period_type}` : g.result === "W" ? "Won" : "Lost"} ${g.team_score}–${g.opponent_score} ${versus(g)}`}
            >
              <span className="result-chip-outcome">{g.result === "OTL" ? "OT" : g.result}</span>
              <span className="result-chip-score">{g.team_score}–{g.opponent_score}</span>
              <span className="result-chip-opp">{versus(g)}</span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function TeamPicker({ teams, value, onPick, label = "Follow a team" }) {
  const sorted = [...teams].sort((a, b) => a.team_name.localeCompare(b.team_name));
  return (
    <label className="team-picker">
      <span>{label}</span>
      <select value={value || ""} onChange={(e) => onPick(e.target.value || null)}>
        <option value="">Choose a team…</option>
        {sorted.map((t) => (
          <option key={t.team_abbrev} value={t.team_abbrev}>{t.team_name}</option>
        ))}
      </select>
    </label>
  );
}

// Your team at a glance, at the top of the Scores page: the season so far,
// playoff odds, the live or next game, and recent results.
function MyTeamCard({ team, odds, teams, onChangeTeam }) {
  const schedule = useTeamSchedule(team.team_abbrev);
  const [changing, setChanging] = useState(false);

  const facts = [
    `${team.wins}-${team.losses}-${team.ot_losses}`,
    `${team.points} PTS`,
    `${ordinal(team.division_sequence)} ${team.division}`,
    team.streak_code ? `${team.streak_code}${team.streak_count} streak` : null,
  ].filter(Boolean);

  return (
    <section className="my-team-card" aria-label={`My team: ${team.team_name}`}>
      <div className="my-team-header">
        <Link className="my-team-identity" to={`/teams/${team.team_abbrev}`}>
          {team.logo_url && <img className="my-team-logo" src={darkLogo(team.logo_url)} alt="" />}
          <span>
            <span className="my-team-kicker">★ My team</span>
            <span className="my-team-name">{team.team_name}</span>
          </span>
        </Link>
        {odds != null && (
          <Link className="my-team-odds" to="/playoffs" aria-label={`Playoff odds ${formatOdds(odds)}, see the playoff race`}>
            <strong>{formatOdds(odds)}</strong>
            <span>playoff odds</span>
          </Link>
        )}
      </div>
      <p className="my-team-facts">{facts.join(" · ")}</p>

      {schedule.data ? (
        <>
          <GameLine schedule={schedule.data} />
          <RecentResults games={schedule.data.recent} />
        </>
      ) : schedule.error ? (
        <p className="my-team-game my-team-game-none">Couldn't load the schedule.</p>
      ) : (
        <p className="my-team-game my-team-game-none">Loading schedule…</p>
      )}

      <div className="my-team-footer">
        {changing ? (
          <>
            <TeamPicker
              teams={teams}
              value={team.team_abbrev}
              label="Switch to"
              onPick={(abbrev) => {
                setChanging(false);
                if (abbrev) onChangeTeam(abbrev);
              }}
            />
            <button type="button" className="link-button" onClick={() => onChangeTeam(null)}>Stop following</button>
          </>
        ) : (
          <>
            <Link className="my-team-sim-link" to={`/teams/${team.team_abbrev}#season-sim`}>Sim the season ›</Link>
            <button type="button" className="link-button" onClick={() => setChanging(true)}>Change team</button>
          </>
        )}
      </div>
    </section>
  );
}

export default MyTeamCard;
