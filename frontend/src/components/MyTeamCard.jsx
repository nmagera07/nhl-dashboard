import { ordinal } from "../utils/ordinal.js";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { teamLogo } from "../utils/teamLogo.js";
import { formatOdds } from "../utils/playoffRace.js";
import { gameTimeLabel } from "../utils/dates.js";
import { cachedResponse, rememberResponse } from "../utils/responseCache.js";
import { formatPct, pointsPace } from "../utils/pointsPace.js";
import GoalAlerts from "./GoalAlerts.jsx";

const LIVE_REFRESH_MS = 30_000;

const versus = (game) => `${game.home ? "vs" : "@"} ${game.opponent}`;

// Loads the team's schedule summary; refreshes every 30s while a game is live.
function useTeamSchedule(abbrev) {
  const url = `${API_BASE}/teams/${abbrev}/schedule`;
  const [state, setState] = useState(() => {
    const cached = cachedResponse(url);
    return cached ? { abbrev, data: cached, error: false } : { abbrev: null, data: null, error: false };
  });

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const load = () =>
      fetch(url)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.status))))
        .then((data) => {
          if (cancelled) return;
          rememberResponse(url, data);
          setState({ abbrev, data, error: false });
          if (data.live) timer = setTimeout(load, LIVE_REFRESH_MS);
        })
        .catch(() => !cancelled && setState((s) => ({ ...s, abbrev, error: true })));
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [abbrev, url]);

  // Ignore a previous team's data while the new team's loads.
  return state.abbrev === abbrev ? state : { data: null, error: false };
}

const STALE_LINE_DAYS = 7;

// The playoff line from the daily sim (GET /playoff-line): once-a-day data,
// shown from the cache first. Never fetches /season-sim.
function usePlayoffLine() {
  const url = `${API_BASE}/playoff-line`;
  const [data, setData] = useState(() => cachedResponse(url) ?? null);
  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.status))))
      .then((body) => {
        if (cancelled || !body || typeof body !== "object" || !body.cutline) return;
        rememberResponse(url, body);
        setData(body);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [url]);
  return data;
}

function isStale(asOf, now = Date.now()) {
  if (!asOf) return true;
  return now - new Date(`${asOf}T12:00:00Z`).getTime() > STALE_LINE_DAYS * 86_400_000;
}

const pts = (n) => (Number.isInteger(n) ? n : n.toFixed(1));

export function PlayoffLine({ data, team }) {
  if (!data || data.games_remaining === 0 || isStale(data.as_of_date)) return null;
  const row = data.teams?.[team.team_abbrev];
  if (!row) return null;
  const pace = pointsPace(data.cutline?.[row.conference], { ...row, clinch_indicator: team.clinch_indicator }, data.season_games);
  if (!pace) return null;

  // One clean line: what it takes, and where the team is headed (named, since
  // "You" read as the viewer). The likely range of the line is in the details.
  const nb = (text) => text.replace(/ /g, "\u00a0");
  const where = pace.pace != null ? nb(`${team.team_abbrev} on pace for ${pace.pace}`) : nb(`${team.team_abbrev} at ${pace.pts}`);
  const headline = `${nb(`Need ~${pts(pace.cutline)} pts`)} · ${where}`;
  const range = pace.low !== pace.high
    ? <p className="my-team-line-range">The line usually lands between {pts(pace.low)} and {pts(pace.high)} points.</p>
    : null;

  let body;
  if (pace.state === "clinched") body = <p className="my-team-line-status my-team-line-in">Clinched ✓</p>;
  else if (pace.state === "above") body = <p className="my-team-line-status my-team-line-in">Above the line</p>;
  else if (pace.state === "eliminated") body = <p className="my-team-line-status my-team-line-out">Eliminated</p>;
  else {
    const { w, l, otl } = pace.record;
    const now = pace.pointPctg ?? 0;
    body = (
      <>
        <div className="my-team-line-bar" role="img" aria-label={`Current points % ${formatPct(pace.pointPctg)}, needed ${formatPct(pace.reqPct)}`}>
          <span className="my-team-line-now" style={{ width: `${Math.min(100, now * 100)}%` }} />
          <span className="my-team-line-need" style={{ left: `${Math.min(100, pace.reqPct * 100)}%` }} />
        </div>
        <p className="my-team-line-need-text">
          Need {pace.ptsNeeded} in {pace.gamesRemaining} GP → {formatPct(pace.reqPct)} (now {formatPct(pace.pointPctg)})
        </p>
        <p className="my-team-line-record">Roughly {w}-{l}-{otl} the rest of the way</p>
      </>
    );
  }

  // Collapsed to one line by default (the card stays short); tap for the details.
  return (
    <details className="my-team-line" aria-label="Playoff line">
      <summary>
        <span className="my-team-game-label">
          Playoff line{pace.early && <span className="my-team-line-early"> · Early estimate</span>}
        </span>
        <span className="my-team-line-headline">{headline}</span>
      </summary>
      {body}
      {range}
    </details>
  );
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
        {next.opponent_logo && <img src={teamLogo(next.opponent_logo)} alt="" />}
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
  const playoffLine = usePlayoffLine();
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
          {team.logo_url && <img className="my-team-logo" src={teamLogo(team.logo_url)} alt="" />}
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
      <PlayoffLine data={playoffLine} team={team} />

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
            <GoalAlerts team={team.team_abbrev} />
            <Link className="my-team-sim-link" to={`/teams/${team.team_abbrev}#season-sim`}>Sim the season ›</Link>
            <button type="button" className="link-button" onClick={() => setChanging(true)}>Change team</button>
          </>
        )}
      </div>
    </section>
  );
}

export default MyTeamCard;
