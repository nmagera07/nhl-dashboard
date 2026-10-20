import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { track } from "../utils/analytics.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import OddsChart from "../components/OddsChart.jsx";
import OddsWhy from "../components/OddsWhy.jsx";
import StatAbbr from "../components/StatAbbr.jsx";
import StatGlossary from "../components/StatGlossary.jsx";
import FavoriteStar from "../components/FavoriteStar.jsx";
import { useFavoriteTeam } from "../hooks/useFavoriteTeam.js";
import { teamLogo } from "../utils/teamLogo.js";
import { formatSeasonLabel } from "../utils/formatSeasonLabel.js";
import { buildSeries, clinchStatus, formatOdds, latestWithChange, raceGroups, seasonGames } from "../utils/playoffRace.js";

const CONFERENCES = ["Eastern", "Western"];
const EMPTY_HISTORY = { season_id: null, available_seasons: [], points: [] };
const EMPTY_WHY = { season_id: null, teams: {} };

function Change({ value }) {
  if (value == null) return <span className="race-change">—</span>;
  const points = Math.round(value * 100);
  if (points === 0) return <span className="race-change">0</span>;
  return (
    <span className={points > 0 ? "race-change race-change-up" : "race-change race-change-down"}>
      {points > 0 ? "▲" : "▼"} {Math.abs(points)}
    </span>
  );
}

function RaceRows({ label, teams, odds, highlighted, onHighlight, why, showChange }) {
  const columns = showChange ? 6 : 5;
  const [favorite] = useFavoriteTeam();
  return (
    <>
      <tr className="race-group">
        <th colSpan={columns} scope="colgroup">{label}</th>
      </tr>
      {teams.map((row) => {
        const status = clinchStatus(row.clinch_indicator);
        const teamOdds = odds[row.team_abbrev];
        const selected = row.team_abbrev === highlighted;
        return (
          <Fragment key={row.team_abbrev}>
            <tr
              className={selected ? "row-selected" : undefined}
              onClick={() => onHighlight(selected ? null : row.team_abbrev)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onHighlight(selected ? null : row.team_abbrev);
                }
              }}
              tabIndex={0}
              aria-selected={selected}
            >
              <td className="col-team">
                <span className="team-cell">
                  <img className="team-cell-logo" src={teamLogo(row.logo_url)} alt="" />
                  <span className="team-abbrev">{row.team_abbrev}</span>
                  {row.team_abbrev === favorite && <FavoriteStar />}
                  {status && <span className={`race-badge race-badge-${status.tone}`} title={status.title}>{status.label}</span>}
                </span>
              </td>
              <td>{row.games_played}</td>
              <td className="col-pts">{row.points}</td>
              <td className="race-col-pace">{Math.round((row.points / Math.max(row.games_played, 1)) * seasonGames(row.season_id))}</td>
              <td className="race-col-odds">
                <span className="race-odds">
                  <span className="race-odds-bar" aria-hidden="true">
                    <span style={{ width: `${(teamOdds?.pct ?? 0) * 100}%` }} />
                  </span>
                  {formatOdds(teamOdds?.pct)}
                </span>
              </td>
              {showChange && <td><Change value={teamOdds?.change} /></td>}
            </tr>
            {selected && why && teamOdds && (
              <tr className="race-why-row">
                <td colSpan={columns}>
                  <OddsWhy pct={teamOdds.pct} why={why.data.teams[row.team_abbrev]} teams={why.teamCount} status={why.status} />
                  <Link className="accent-link race-team-page" to={`/teams/${row.team_abbrev}`}>{row.team_abbrev} team page ›</Link>
                </td>
              </tr>
            )}
          </Fragment>
        );
      })}
    </>
  );
}

// The playoff race for one conference: odds over the season as a chart,
// and the current standings laid out in the playoff format (division top
// 3s, two wild cards, then everyone chasing), with each team's odds and
// how they've moved this week.
function PlayoffsPage({ standings, standingsStatus = "ready" }) {
  const [conference, setConference] = useState("Eastern");
  const [chartSeason, setChartSeason] = useState(null); // null = the latest season with odds
  const [highlighted, setHighlighted] = useState(null);
  // The "why these odds?" breakdown loads the first time a team is opened.
  const [wantWhy, setWantWhy] = useState(false);
  const highlight = (team) => {
    setHighlighted(team);
    if (team) {
      setWantWhy(true);
      track("odds-why", { team });
    }
  };

  const { data: latest, status } = useFetchWithStatus(`${API_BASE}/playoff-odds/history`, { initialData: EMPTY_HISTORY });
  const { data: whyData, status: whyStatus } = useFetchWithStatus(wantWhy ? `${API_BASE}/playoff-odds/why` : null, { initialData: EMPTY_WHY });
  const otherSeasonUrl = chartSeason && chartSeason !== latest.season_id
    ? `${API_BASE}/playoff-odds/history?season_id=${chartSeason}`
    : null;
  const { data: other, status: otherStatus } = useFetchWithStatus(otherSeasonUrl, { initialData: EMPTY_HISTORY });
  const showingOther = otherSeasonUrl != null;
  const chartHistory = showingOther ? other : latest;

  // Odds only count if they're from the same season as the standings (in
  // the offseason, the latest odds are last season's).
  const currentSeason = standings[0]?.season_id;
  const odds = useMemo(
    () => (latest.season_id === currentSeason ? latestWithChange(latest.points) : {}),
    [latest, currentSeason]
  );
  // The 7d column needs a snapshot from a week back; early in a season
  // there isn't one yet, and a column of dashes looks broken.
  const showChange = Object.values(odds).some((o) => o.change != null);

  // Same season check as the odds: no breakdown for last season's numbers.
  const why = Object.keys(odds).length
    ? {
        data: whyData.season_id === currentSeason ? whyData : EMPTY_WHY,
        status: whyStatus,
        teamCount: standings.length,
      }
    : null;

  const confRows = useMemo(() => standings.filter((r) => r.conference === conference), [standings, conference]);
  const groups = useMemo(() => raceGroups(confRows), [confRows]);
  const chart = useMemo(
    () => buildSeries(chartHistory.points, confRows.map((r) => r.team_abbrev)),
    [chartHistory, confRows]
  );

  const selectConference = (c) => {
    setConference(c);
    highlight(null);
  };

  const seasons = latest.available_seasons.slice(0, 2);
  // The season fetch starts "idle" (no URL) and only flips to ready once it
  // lands, so anything short of ready/error means it's still loading.
  const chartLoading = showingOther ? !["ready", "error"].includes(otherStatus) : status === "loading";

  return (
    <main className="playoffs-page">
      <div className="page-header page">
        <h1>Playoff race</h1>
        <Link className="accent-link playoffs-lottery-link" to="/draft-lottery">Draft lottery ›</Link>
      </div>
      <div className="race-controls">
        <div className="view-toggle" role="group" aria-label="Conference">
          {CONFERENCES.map((c) => (
            <button
              key={c}
              type="button"
              className={c === conference ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"}
              aria-pressed={c === conference}
              onClick={() => selectConference(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Collapsed by default: the table is the page; the chart is for whoever wants the history. */}
      <details className="race-card race-chart-details">
        <summary className="race-card-header">
          <h2 id="race-chart-title">Odds over the season</h2>
          {seasons.length > 1 && (
            <div className="view-toggle" role="group" aria-label="Chart season">
              {seasons.map((s) => {
                const active = s === (chartSeason ?? latest.season_id);
                return (
                  <button
                    key={s}
                    type="button"
                    className={active ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"}
                    aria-pressed={active}
                    onClick={() => setChartSeason(s)}
                  >
                    {formatSeasonLabel(s)}
                  </button>
                );
              })}
            </div>
          )}
        </summary>
        {status === "error" || (showingOther && otherStatus === "error") ? (
          <p className="status-line status-error">Couldn't load playoff odds.</p>
        ) : chartLoading ? (
          <p className="status-line">Loading odds…</p>
        ) : chart.dates.length < 2 ? (
          <p className="race-empty">
            The chart fills in as the season goes. The odds update every morning.
            {seasons.length > 1 && !showingOther && (
              <> <button type="button" className="link-button" onClick={() => setChartSeason(seasons[1])}>See last season's race</button></>
            )}
          </p>
        ) : (
          <OddsChart dates={chart.dates} series={chart.series} highlighted={highlighted} onHighlight={highlight} />
        )}
      </details>

      <section className="race-card race-table-card" aria-labelledby="race-table-title">
        <div className="race-card-header">
          <h2 id="race-table-title">Where it stands</h2>
          {why && <p className="race-hint">Tap a team to see why</p>}
        </div>
        {standingsStatus !== "ready" && standings.length === 0 ? (
          <p className={standingsStatus === "error" ? "status-line status-error" : "status-line"}>
            {standingsStatus === "error" ? "Couldn't load the standings." : "Loading standings…"}
          </p>
        ) : (
        <div className="race-table-scroll">
          <table className="standings-table race-table">
            <thead>
              <tr>
                <th className="col-team" scope="col">Team</th>
                <th scope="col"><StatAbbr term="GP" /></th>
                <th scope="col"><StatAbbr term="TEAM_PTS">PTS</StatAbbr></th>
                <th scope="col" className="race-col-pace"><StatAbbr term="PACE">Pace</StatAbbr></th>
                <th scope="col" className="race-col-odds"><StatAbbr term="PO%" /></th>
                {showChange && <th scope="col"><StatAbbr term="7D">7d</StatAbbr></th>}
              </tr>
            </thead>
            <tbody>
              {groups.divisions.map((d) => (
                <RaceRows key={d.name} label={d.name} teams={d.teams} odds={odds} highlighted={highlighted} onHighlight={highlight} why={why} showChange={showChange} />
              ))}
              <RaceRows label="Wild card" teams={groups.wildcards} odds={odds} highlighted={highlighted} onHighlight={highlight} why={why} showChange={showChange} />
              <tr className="race-cutline" aria-hidden="true"><td colSpan={showChange ? 6 : 5} /></tr>
              <RaceRows label="Chasing" teams={groups.chasing} odds={odds} highlighted={highlighted} onHighlight={highlight} why={why} showChange={showChange} />
            </tbody>
          </table>
        </div>
        )}
      </section>

      <StatGlossary terms={showChange ? ["GP", "TEAM_PTS", "PACE", "PO%", "7D"] : ["GP", "TEAM_PTS", "PACE", "PO%"]} labels={{ TEAM_PTS: "PTS", PACE: "Pace", "7D": "7d" }} />
      <p className="data-credit">
        Odds from 10,000 simulations of the rest of the season, blending goals with PuckPulse&apos;s own expected goals
        (xG, from NHL play-by-play) and each roster&apos;s players. Player and goalie data courtesy of{" "}
        <a href="https://moneypuck.com" target="_blank" rel="noreferrer">MoneyPuck.com</a>.
        {" "}<Link className="accent-link" to="/track-record">How accurate is the model?</Link>
      </p>
    </main>
  );
}

export default PlayoffsPage;
