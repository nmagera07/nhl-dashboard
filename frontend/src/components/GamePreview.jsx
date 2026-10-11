import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { winProbability } from "../utils/seasonSim.js";
import { formatOdds } from "../utils/playoffRace.js";

const pct = (v, digits = 1) => (v == null ? "—" : `${(Number(v) * 100).toFixed(digits)}%`);
const num = (v, digits = 2) => (v == null ? "—" : Number(v).toFixed(digits));
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
const rank = (r) => (r ? ` (${ordinal(r)})` : "");

// Team season stats from the NHL's pregame feed; ranks are league-wide (1st = best).
const SEASON_STATS = [
  { key: "goalsForPerGamePlayed", label: "Goals for / game", format: (v) => num(v) },
  { key: "goalsAgainstPerGamePlayed", label: "Goals against / game", format: (v) => num(v), lowerIsBetter: true },
  { key: "ppPctg", label: "Power play", format: (v) => pct(v) },
  { key: "pkPctg", label: "Penalty kill", format: (v) => pct(v) },
  { key: "faceoffWinningPctg", label: "Faceoffs", format: (v) => pct(v) },
];
const SKATER_LABELS = { points: "Points", goals: "Goals", assists: "Assists" };
const RESULT = { W: "W", L: "L", OTL: "OT", SOL: "SO" };

function WinProbability({ away, home }) {
  const { data: inputs } = useFetchWithStatus(`${API_BASE}/season-sim`);
  const a = inputs?.teams?.[away.abbrev];
  const h = inputs?.teams?.[home.abbrev];
  if (!a || !h || !inputs.model) return null;
  const homeWin = winProbability(h.rating, a.rating, inputs.model);
  const homePct = Math.round(homeWin * 100);
  return (
    <section className="boxscore-card preview-odds" aria-label="Win probability">
      <h2>Win probability</h2>
      <div className="preview-odds-teams">
        <span><strong>{100 - homePct}%</strong> {away.abbrev}</span>
        <span>{home.abbrev} <strong>{homePct}%</strong></span>
      </div>
      <div className="preview-odds-bar" role="img" aria-label={`${away.abbrev} ${100 - homePct}% chance to win, ${home.abbrev} ${homePct}%`}>
        <span style={{ width: `${100 - homePct}%` }} />
      </div>
      <p className="preview-note">
        PuckPulse&apos;s model: each team&apos;s goals and expected-goals rating, plus home ice. Single games are
        close to coin flips, so treat it as a lean, not a lock. For fun and insight, not betting advice.{" "}
        <Link className="accent-link" to="/track-record">See how the model has done.</Link>
      </p>
    </section>
  );
}

function CompareRow({ label, awayValue, homeValue, awayBetter, homeBetter }) {
  return (
    <div className="team-stats-row">
      <span className={awayBetter ? "preview-better" : undefined}>{awayValue}</span>
      <div className="team-stats-label"><span>{label}</span></div>
      <span className={homeBetter ? "preview-better" : undefined}>{homeValue}</span>
    </div>
  );
}

function Form({ last10, team }) {
  if (!last10) return <span className="muted">—</span>;
  return (
    <div className="preview-form">
      <span className="preview-form-record">
        {last10.record}{last10.streakType ? ` · ${last10.streakType}${last10.streak}` : ""}
      </span>
      <ol aria-label={`${team} recent results, newest first`}>
        {(last10.pastGameResults || []).slice(0, 5).map((g, i) => (
          <li key={i} className={`preview-result preview-result-${(RESULT[g.gameResult] || g.gameResult).toLowerCase()}`} title={`${g.gameResult} vs ${g.opponentAbbrev}`}>
            {RESULT[g.gameResult] || g.gameResult}
          </li>
        ))}
      </ol>
    </div>
  );
}

const leaderName = (l) => (l ? `${l.name?.default || ""} · ${l.value}` : "—");
const goalieLine = (g) => (g ? `${g.name?.default} · ${g.record} · ${num(g.gaa)} GAA · ${num(g.savePctg, 3)}` : "—");

// Before puck drop: who's favored, how each team is doing, and who to watch.
// Everything except the win probability comes from the NHL's pregame feed.
function GamePreview({ game, standingsByTeam = {}, playoffOddsByTeam = {} }) {
  const away = game.awayTeam;
  const home = game.homeTeam;
  const stats = game.teamSeasonStats || {};
  const leaders = game.matchup?.skaterComparison?.leaders || [];
  const goalies = game.matchup?.goalieComparison || {};
  const series = (game.seasonSeries || []).filter((g) => g.id !== game.id);
  const wins = game.seasonSeriesWins || {};
  const row = (t) => standingsByTeam[t.abbrev];
  const place = (r) => (r ? `${ordinal(r.division_sequence)} ${r.division}` : "—");

  return (
    <>
      <WinProbability away={away} home={home} />

      <section className="boxscore-card">
        <h2>Matchup</h2>
        <div className="team-stats preview-compare">
          <div className="team-stats-row team-stats-header">
            <strong>{away.abbrev}</strong><span /><strong>{home.abbrev}</strong>
          </div>
          <CompareRow label="Division" awayValue={place(row(away))} homeValue={place(row(home))} />
          <CompareRow label="Playoff odds" awayValue={formatOdds(playoffOddsByTeam[away.abbrev])} homeValue={formatOdds(playoffOddsByTeam[home.abbrev])} />
          <div className="team-stats-row">
            <Form last10={game.last10Record?.awayTeam} team={away.abbrev} />
            <div className="team-stats-label"><span>Last 10</span></div>
            <Form last10={game.last10Record?.homeTeam} team={home.abbrev} />
          </div>
          {SEASON_STATS.map(({ key, label, format, lowerIsBetter }) => {
            const av = stats.awayTeam?.[key];
            const hv = stats.homeTeam?.[key];
            if (av == null && hv == null) return null;
            const better = av != null && hv != null && av !== hv ? ((av > hv) !== Boolean(lowerIsBetter) ? "away" : "home") : null;
            return (
              <CompareRow key={key} label={label}
                awayValue={`${format(av)}${rank(stats.awayTeam?.[`${key}Rank`])}`}
                homeValue={`${format(hv)}${rank(stats.homeTeam?.[`${key}Rank`])}`}
                awayBetter={better === "away"} homeBetter={better === "home"} />
            );
          })}
        </div>
        <p className="preview-note">Ranks are league-wide (1st = best).</p>
      </section>

      {(leaders.length > 0 || goalies.awayTeam || goalies.homeTeam) && (
        <section className="boxscore-card">
          <h2>Players to watch</h2>
          <div className="team-stats preview-compare">
            {leaders.map((l) => (
              <CompareRow key={l.category} label={SKATER_LABELS[l.category] || l.category} awayValue={leaderName(l.awayLeader)} homeValue={leaderName(l.homeLeader)} />
            ))}
            <CompareRow label="Goalie" awayValue={goalieLine(goalies.awayTeam?.leaders?.[0])} homeValue={goalieLine(goalies.homeTeam?.leaders?.[0])} />
          </div>
        </section>
      )}

      {series.length > 0 && (
        <section className="boxscore-card">
          <h2>Season series</h2>
          <p className="preview-series-score">
            {away.abbrev} {wins.awayTeamWins ?? 0} – {wins.homeTeamWins ?? 0} {home.abbrev}
          </p>
          <ul className="preview-series">
            {series.map((g) => (
              <li key={g.id}>
                <span>{g.gameDate}</span>
                <span>
                  {g.awayTeam?.abbrev} {g.awayTeam?.score ?? ""} @ {g.homeTeam?.abbrev} {g.homeTeam?.score ?? ""}
                </span>
                <span className="muted">{g.gameState === "FUT" || g.gameState === "PRE" ? "Upcoming" : "Final"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export default GamePreview;
