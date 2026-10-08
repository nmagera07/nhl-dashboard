import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { API_BASE } from "../config.js";

// Live games refetch on this interval so the score, clock, and stats stay current.
const LIVE_REFRESH_MS = 30000;
const LIVE_STATES = new Set(["LIVE", "CRIT"]);
const FINAL_STATES = new Set(["FINAL", "OFF"]);

// Team stat categories from the NHL's right-rail feed, in display order.
// faceoffWins and powerPlayPctg duplicate faceoffWinningPctg and powerPlay.
const TEAM_STATS = [
  { category: "sog", label: "Shots on goal" },
  { category: "faceoffWinningPctg", label: "Faceoff %", format: (v) => `${(Number(v) * 100).toFixed(1)}%` },
  { category: "powerPlay", label: "Power play" },
  { category: "pim", label: "Penalty minutes" },
  { category: "hits", label: "Hits" },
  { category: "blockedShots", label: "Blocked shots" },
  { category: "giveaways", label: "Giveaways" },
  { category: "takeaways", label: "Takeaways" },
];

const STRENGTH_LABELS = { pp: "PP", sh: "SH" };

const ordinal = (n) => ["1st", "2nd", "3rd"][n - 1] || `${n}th`;

// Short label for linescore column headers: 1, 2, 3, OT, 2OT, SO.
function periodShort(pd) {
  if (!pd) return "";
  if (pd.periodType === "SO") return "SO";
  if (pd.periodType === "OT") {
    const otNumber = pd.number - (pd.maxRegulationPeriods || 3);
    return otNumber > 1 ? `${otNumber}OT` : "OT";
  }
  return String(pd.number);
}

// Long label for headings and the live status: 1st Period, OT, 2OT, Shootout.
function periodLong(pd) {
  if (!pd) return "";
  if (pd.periodType === "SO") return "Shootout";
  if (pd.periodType === "OT") return periodShort(pd);
  return `${ordinal(pd.number)} Period`;
}

function gameStatus(game) {
  if (LIVE_STATES.has(game.gameState)) {
    const period = periodShort(game.periodDescriptor);
    const periodText = /^\d+$/.test(period) ? ordinal(Number(period)) : period;
    if (game.clock?.inIntermission) return `${periodText} intermission`;
    return `${periodText} · ${game.clock?.timeRemaining ?? ""}`.trim();
  }
  if (FINAL_STATES.has(game.gameState)) {
    const last = game.gameOutcome?.lastPeriodType;
    return last === "OT" || last === "SO" ? `Final/${last}` : "Final";
  }
  if (game.startTimeUTC) {
    return new Date(game.startTimeUTC).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
  }
  return game.gameState || "";
}

const teamName = (team) => [team?.placeName?.default, team?.commonName?.default].filter(Boolean).join(" ") || team?.abbrev || "Team";
const abbrevOf = (value) => (typeof value === "string" ? value : value?.default) || "";
const nameOf = (value) => value?.default || "";

function savePct(goalie) {
  if (!goalie.shotsAgainst) return "—";
  return (goalie.saves / goalie.shotsAgainst).toFixed(3).replace(/^0/, "");
}

function TeamHeader({ team, side }) {
  return (
    <div className={`game-team game-team-${side}`}>
      {team?.darkLogo && <img className="game-team-logo" src={team.darkLogo} alt="" />}
      <span className="game-team-abbrev">{team?.abbrev}</span>
      <span className="game-team-name">{teamName(team)}</span>
    </div>
  );
}

function PeriodTable({ title, periods, away, home, totals }) {
  return (
    <div className="boxscore-table-wrap">
      <table className="boxscore-table linescore-table" aria-label={title}>
        <thead>
          <tr>
            <th className="col-team">{title}</th>
            {periods.map((period, i) => <th key={i}>{periodShort(period.periodDescriptor)}</th>)}
            <th>T</th>
          </tr>
        </thead>
        <tbody>
          {[["away", away], ["home", home]].map(([side, team]) => (
            <tr key={side}>
              <td className="col-team">{team?.abbrev}</td>
              {periods.map((period, i) => <td key={i}>{period[side] ?? "—"}</td>)}
              <td className="linescore-total">{totals[side] ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScoringSummary({ scoring, away, home }) {
  const periods = scoring.filter((period) => (period.goals || []).length > 0);
  if (periods.length === 0) return <p className="muted">No goals yet.</p>;
  return periods.map((period, index) => (
    <div className="scoring-period" key={period.periodDescriptor?.number ?? index}>
      <div className="trend-eyebrow">{periodLong(period.periodDescriptor).toUpperCase()}</div>
      {period.goals.map((goal, goalIndex) => {
        const team = abbrevOf(goal.teamAbbrev);
        const strength = STRENGTH_LABELS[goal.strength];
        const assists = (goal.assists || []).map((a) => `${nameOf(a.name)} (${a.assistsToDate})`).join(", ");
        return (
          <div className="goal-row" key={goal.eventId ?? goalIndex}>
            <span className="goal-time">{goal.timeInPeriod}</span>
            <span className={`goal-team${team === home?.abbrev ? " goal-team-home" : ""}`}>{team}</span>
            <span className="goal-detail">
              <span>
                <strong>
                  {nameOf(goal.name)}
                  {goal.goalsToDate != null && ` (${goal.goalsToDate})`}
                </strong>
                {strength && <span className="goal-tag">{strength}</span>}
                {goal.goalModifier === "empty-net" && <span className="goal-tag">EN</span>}
                {goal.goalModifier === "penalty-shot" && <span className="goal-tag">PS</span>}
              </span>
              <small>{assists ? `Assists: ${assists}` : "Unassisted"}</small>
            </span>
            {goal.awayScore != null && (
              <span className="goal-score">{away?.abbrev} {goal.awayScore}–{goal.homeScore} {home?.abbrev}</span>
            )}
          </div>
        );
      })}
    </div>
  ));
}

function ThreeStars({ stars }) {
  return (
    <ol className="three-stars">
      {stars.map((star) => (
        <li key={star.star}>
          <span className="three-stars-rank">{"★".repeat(star.star)}</span>
          <strong>{nameOf(star.name)}</strong>
          <span className="muted">{abbrevOf(star.teamAbbrev)} · {star.position}</span>
          <span className="three-stars-line">
            {star.position === "G"
              ? star.savePctg != null ? `${Number(star.savePctg).toFixed(3).replace(/^0/, "")} SV%` : ""
              : `${star.goals ?? 0} G, ${star.assists ?? 0} A`}
          </span>
        </li>
      ))}
    </ol>
  );
}

function TeamStats({ stats, away, home }) {
  const byCategory = Object.fromEntries(stats.map((stat) => [stat.category, stat]));
  const rows = TEAM_STATS.filter(({ category }) => byCategory[category]);
  return (
    <div className="team-stats">
      <div className="team-stats-row team-stats-header">
        <strong>{away?.abbrev}</strong>
        <span />
        <strong>{home?.abbrev}</strong>
      </div>
      {rows.map(({ category, label, format }) => {
        const { awayValue, homeValue } = byCategory[category];
        const numeric = typeof awayValue === "number" && typeof homeValue === "number";
        const total = numeric ? awayValue + homeValue : 0;
        const awayShare = total > 0 ? (awayValue / total) * 100 : 50;
        return (
          <div className="team-stats-row" key={category}>
            <span>{format ? format(awayValue) : awayValue}</span>
            <div className="team-stats-label">
              <span>{label}</span>
              {numeric && (
                <div className="team-stats-bar" aria-hidden="true">
                  <div className="team-stats-bar-away" style={{ width: `${awayShare}%` }} />
                </div>
              )}
            </div>
            <span>{format ? format(homeValue) : homeValue}</span>
          </div>
        );
      })}
    </div>
  );
}

function SkaterTable({ title, players }) {
  if (!players?.length) return null;
  return (
    <div className="boxscore-table-wrap">
      <table className="boxscore-table player-table" aria-label={title}>
        <thead>
          <tr>
            <th className="col-team">{title}</th>
            <th>G</th>
            <th>A</th>
            <th>P</th>
            <th>+/-</th>
            <th>SOG</th>
            <th>HIT</th>
            <th>BLK</th>
            <th>PIM</th>
            <th>TOI</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => (
            <tr key={p.playerId}>
              <td className="col-team">
                <Link to={`/players/${p.playerId}`}>
                  <span className="player-number">{p.sweaterNumber}</span>
                  {nameOf(p.name)}
                </Link>
              </td>
              <td>{p.goals}</td>
              <td>{p.assists}</td>
              <td className="col-pts">{p.points}</td>
              <td>{p.plusMinus > 0 ? `+${p.plusMinus}` : p.plusMinus}</td>
              <td>{p.sog}</td>
              <td>{p.hits}</td>
              <td>{p.blockedShots}</td>
              <td>{p.pim}</td>
              <td>{p.toi}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GoalieTable({ goalies }) {
  // The backup is listed with 00:00 TOI when he didn't play.
  const played = (goalies || []).filter((g) => g.toi && g.toi !== "00:00");
  if (played.length === 0) return null;
  return (
    <div className="boxscore-table-wrap">
      <table className="boxscore-table player-table" aria-label="Goalies">
        <thead>
          <tr>
            <th className="col-team">Goalies</th>
            <th>SA</th>
            <th>SV</th>
            <th>GA</th>
            <th>SV%</th>
            <th>TOI</th>
          </tr>
        </thead>
        <tbody>
          {played.map((g) => (
            <tr key={g.playerId}>
              <td className="col-team">
                <Link to={`/players/${g.playerId}`}>
                  <span className="player-number">{g.sweaterNumber}</span>
                  {nameOf(g.name)}
                </Link>
              </td>
              <td>{g.shotsAgainst}</td>
              <td>{g.saves}</td>
              <td>{g.goalsAgainst}</td>
              <td className="col-pts">{savePct(g)}</td>
              <td>{g.toi}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlayerStats({ playerStats, away, home }) {
  const [side, setSide] = useState("awayTeam");
  const team = side === "awayTeam" ? away : home;
  const stats = playerStats[side] || {};
  return (
    <>
      <div className="game-team-tabs" role="tablist" aria-label="Team">
        {[["awayTeam", away], ["homeTeam", home]].map(([key, t]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={side === key}
            className={`division-tab${side === key ? " division-tab-active" : ""}`}
            onClick={() => setSide(key)}
          >
            {t?.abbrev}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={`${team?.abbrev} players`}>
        <SkaterTable title="Forwards" players={stats.forwards} />
        <SkaterTable title="Defense" players={stats.defense} />
        <GoalieTable goalies={stats.goalies} />
      </div>
    </>
  );
}

export default function GamePage() {
  const { gameId } = useParams();
  const location = useLocation();
  // Back to the scoreboard day this game was opened from (defaults to today).
  const backTo = location.state?.from || "/";
  const [game, setGame] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    return fetch(`${API_BASE}/games/${gameId}/boxscore`)
      .then((response) => response.ok ? response.json() : response.json().then((body) => Promise.reject(new Error(body.detail))))
      .then((data) => {
        setGame(data);
        setError("");
      });
  }, [gameId]);

  useEffect(() => {
    load().catch((requestError) => setError(requestError.message || "Could not load this box score."));
  }, [load]);

  const isLive = LIVE_STATES.has(game?.gameState);
  useEffect(() => {
    if (!isLive) return undefined;
    // A failed refresh keeps showing the last good data rather than an error.
    const timer = setInterval(() => load().catch(() => {}), LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [isLive, load]);

  if (error) return <div className="page-message status-error">{error}</div>;
  if (!game) return <div className="page-message">Loading box score…</div>;

  const away = game.awayTeam;
  const home = game.homeTeam;
  const started = isLive || FINAL_STATES.has(game.gameState);
  const linescore = game.linescore?.byPeriod || [];
  const shotsByPeriod = game.shotsByPeriod || [];
  const scoring = game.summary?.scoring || [];
  const threeStars = game.summary?.threeStars || [];
  const teamStats = game.teamGameStats || [];
  const playerStats = game.playerByGameStats || {};
  const hasPlayerStats = Boolean(playerStats.awayTeam || playerStats.homeTeam);
  const shotTotals = {
    away: shotsByPeriod.reduce((sum, p) => sum + (p.away || 0), 0),
    home: shotsByPeriod.reduce((sum, p) => sum + (p.home || 0), 0),
  };

  return (
    <main className="game-page">
      <Link className="back-link" to={backTo}>← Scores</Link>

      <div className="game-hero">
        <span className={`game-status${isLive ? " game-status-live" : ""}`}>
          {isLive && <span className="live-dot" />}
          {gameStatus(game)}
        </span>
        <div className="game-scoreboard">
          <TeamHeader team={away} side="away" />
          <div className="game-score">
            {started ? (
              <>
                <strong>{away?.score ?? 0}</strong>
                <span className="game-score-separator">–</span>
                <strong>{home?.score ?? 0}</strong>
              </>
            ) : (
              <span className="game-score-separator">vs</span>
            )}
          </div>
          <TeamHeader team={home} side="home" />
        </div>
        <p>{game.venue?.default ? `${game.venue.default} · ` : ""}{game.gameDate}</p>
      </div>

      {!started && (
        <section className="boxscore-card">
          <p className="muted">This game hasn&apos;t started yet. The box score fills in once the puck drops.</p>
        </section>
      )}

      {linescore.length > 0 && (
        <section className="boxscore-card">
          <h2>Box score</h2>
          <PeriodTable title="Goals" periods={linescore} away={away} home={home} totals={game.linescore?.totals || {}} />
          {shotsByPeriod.length > 0 && (
            <PeriodTable title="Shots" periods={shotsByPeriod} away={away} home={home} totals={shotTotals} />
          )}
        </section>
      )}

      {started && (
        <section className="boxscore-card">
          <h2>Scoring</h2>
          <ScoringSummary scoring={scoring} away={away} home={home} />
        </section>
      )}

      {threeStars.length > 0 && (
        <section className="boxscore-card">
          <h2>Three stars</h2>
          <ThreeStars stars={threeStars} />
        </section>
      )}

      {teamStats.length > 0 && (
        <section className="boxscore-card">
          <h2>Team stats</h2>
          <TeamStats stats={teamStats} away={away} home={home} />
        </section>
      )}

      {started && hasPlayerStats && (
        <section className="boxscore-card">
          <h2>Player stats</h2>
          <PlayerStats playerStats={playerStats} away={away} home={home} />
        </section>
      )}
    </main>
  );
}
