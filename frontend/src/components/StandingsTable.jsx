import { Fragment } from "react";
import { teamLogo } from "../utils/teamLogo.js";
import { formatOdds } from "../utils/playoffRace.js";
import { useFollowedTeams } from "../hooks/useFavoriteTeam.js";
import FavoriteStar from "./FavoriteStar.jsx";
import StatAbbr from "./StatAbbr.jsx";

function StreakBadge({ code, count }) {
  if (!code) return <span className="streak streak-none">—</span>;
  const cls = code === "W" ? "streak streak-w" : code === "L" ? "streak streak-l" : "streak streak-ot";
  return <span className={cls}>{code}{count}</span>;
}

function PlayoffOddsCell({ pct }) {
  if (pct == null) return <td className="col-po">—</td>;
  const value = Number(pct) * 100;
  return (
    <td className={value >= 50 ? "col-po po-in" : "col-po po-out"}>
      {formatOdds(pct)}
    </td>
  );
}

const ADVANCED_SORT_COLUMNS = [
  { key: "xgoals_for_pct", label: "xG%" },
  { key: "xgoals_for", label: "xGF" },
  { key: "xgoals_against", label: "xGA" },
  { key: "shots_on_goal_for", label: "SF" },
  { key: "shots_on_goal_against", label: "SA" },
  { key: "pdo", label: "PDO" },
];

function formatAdvancedValue(key, value) {
  if (value == null) return "—";
  if (key === "pdo") return Number(value).toFixed(1);
  if (key === "xgoals_for_pct") return `${(Number(value) * 100).toFixed(1)}%`;
  if (key === "xgoals_for" || key === "xgoals_against") return Number(value).toFixed(1);
  return value; // shots_on_goal_for/against are plain integer counts
}

// Sorted here, not by the API: every row already has every stat, and PO%
// comes from the playoff odds, not the standings. Ties keep league order,
// and a missing value sorts last either way.
function sortValue(row, key, playoffOddsByTeam) {
  const value = key === "playoff_odds" ? playoffOddsByTeam?.[row.team_abbrev] : row[key];
  return value == null ? null : Number(value);
}

function sortRows(rows, sortBy, sortDir, playoffOddsByTeam) {
  const sign = sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = sortValue(a, sortBy, playoffOddsByTeam);
    const y = sortValue(b, sortBy, playoffOddsByTeam);
    if (x === y) return a.league_sequence - b.league_sequence;
    if (x == null) return 1;
    if (y == null) return -1;
    return sign * (x - y);
  });
}

function SortHeader({ sortKey, sortBy, sortDir, onSort, className = "", children }) {
  const active = sortKey === sortBy;
  return (
    <th
      className={`${className} sortable-col${active ? " sortable-col-active" : ""}`.trim()}
      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
      onClick={() => onSort(sortKey)}
    >
      {children}{active ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
    </th>
  );
}

function TeamCell({ row, following }) {
  return (
    <td className="col-team">
      <span className="team-cell">
        {row.logo_url ? <img className="team-cell-logo" src={teamLogo(row.logo_url)} alt="" /> : <span className="team-cell-logo" />}
        <span className="team-abbrev">{row.team_abbrev}</span>
        <span className="team-name">{row.team_name}</span>
        {following.includes(row.team_abbrev) && <FavoriteStar />}
      </span>
    </td>
  );
}

// cutoff: mark where the division's guaranteed playoff spots end (a
// division tab, not searching): the top 3 are in, the rest race for the wild cards.
function StandingsTable({ rows, onSelectTeam, playoffOddsByTeam, sortBy, sortDir, onSort, view = "standard", rankBy = "division_sequence", cutoff = false }) {
  const [following] = useFollowedTeams();
  // Copy before sorting so this never mutates the rows prop in place.
  const displayRows = sortBy ? sortRows(rows, sortBy, sortDir, playoffOddsByTeam) : [...rows].sort((a, b) => a[rankBy] - b[rankBy]);
  // While sorted by a stat, the rank is the place in that stat.
  const rank = (row, i) => (sortBy ? i + 1 : row[rankBy]);
  const sort = { sortBy, sortDir, onSort };
  const advanced = view === "advanced";
  // rank + team + the view's stat columns
  const columnCount = 2 + (advanced ? 2 + ADVANCED_SORT_COLUMNS.length : 12);

  return (
    <>
    <div className="table-card standings-table-card">
      <table className={advanced ? "standings-table standings-table-advanced" : "standings-table"}>
        <thead>
          <tr>
            <th className="col-rank"></th>
            <th className="col-team">TEAM</th>
            <SortHeader sortKey="games_played" {...sort}><StatAbbr term="GP" /></SortHeader>
            {advanced ? (
              <>
                <SortHeader sortKey="points" className="col-pts" {...sort}><StatAbbr term="TEAM_PTS">PTS</StatAbbr></SortHeader>
                {ADVANCED_SORT_COLUMNS.map((col) => (
                  <SortHeader key={col.key} sortKey={col.key} {...sort}><StatAbbr term={col.label} /></SortHeader>
                ))}
              </>
            ) : (
              <>
                <SortHeader sortKey="wins" {...sort}><StatAbbr term="W" /></SortHeader>
                <SortHeader sortKey="losses" {...sort}><StatAbbr term="TEAM_L">L</StatAbbr></SortHeader>
                <SortHeader sortKey="ot_losses" {...sort}><StatAbbr term="OT" /></SortHeader>
                <SortHeader sortKey="points" className="col-pts" {...sort}><StatAbbr term="TEAM_PTS">PTS</StatAbbr></SortHeader>
                <SortHeader sortKey="goal_for" {...sort}><StatAbbr term="GF" /></SortHeader>
                <SortHeader sortKey="goal_against" {...sort}><StatAbbr term="GA" /></SortHeader>
                <SortHeader sortKey="goal_differential" {...sort}><StatAbbr term="DIFF" /></SortHeader>
                <th><StatAbbr term="L10" /></th>
                <th><StatAbbr term="STRK" /></th>
                <SortHeader sortKey="playoff_odds" className="col-po" {...sort}><StatAbbr term="PO%" /></SortHeader>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {displayRows.length === 0 && (
            <tr>
              <td colSpan={columnCount} className="no-results">
                No teams match your search.
              </td>
            </tr>
          )}
          {displayRows.map((row, i) => (
            <tr key={row.team_abbrev} onClick={() => onSelectTeam(row.team_abbrev)}>
              <td className="col-rank">{rank(row, i)}</td>
              <TeamCell row={row} following={following} />
              <td>{row.games_played}</td>
              {advanced ? (
                <>
                  <td className="col-pts">{row.points}</td>
                  {ADVANCED_SORT_COLUMNS.map((col) => (
                    <td key={col.key} className={col.key === sortBy ? "col-pts" : ""}>
                      {formatAdvancedValue(col.key, row[col.key])}
                    </td>
                  ))}
                </>
              ) : (
                <>
                  <td>{row.wins}</td>
                  <td>{row.losses}</td>
                  <td>{row.ot_losses}</td>
                  <td className="col-pts">{row.points}</td>
                  <td>{row.goal_for}</td>
                  <td>{row.goal_against}</td>
                  <td className={row.goal_differential >= 0 ? "diff-pos" : "diff-neg"}>
                    {row.goal_differential > 0 ? "+" : ""}{row.goal_differential}
                  </td>
                  <td>{row.l10_wins}-{row.l10_losses}-{row.l10_ot_losses}</td>
                  <td><StreakBadge code={row.streak_code} count={row.streak_count} /></td>
                  <PlayoffOddsCell pct={playoffOddsByTeam?.[row.team_abbrev]} />
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    <div className="standings-mobile-list" aria-label="Team standings">
      {displayRows.length === 0 && <div className="standings-mobile-empty">No teams match your search.</div>}
      {displayRows.map((row, i) => {
        const odds = playoffOddsByTeam?.[row.team_abbrev];
        const streak = row.streak_code ? ` · ${row.streak_code}${row.streak_count}` : "";
        return (
          <Fragment key={row.team_abbrev}>
            {cutoff && i === 3 && <div className="standings-cutoff" role="separator">Wild-card race</div>}
            <button
              className="standings-row"
              type="button"
              aria-label={`Open ${row.team_name} team page`}
              onClick={() => onSelectTeam(row.team_abbrev)}
            >
              <span className="standings-row-rank">{rank(row, i)}</span>
              {row.logo_url ? <img className="standings-row-logo" src={teamLogo(row.logo_url)} alt="" /> : <span className="standings-row-logo" />}
              <span className="standings-row-team">
                <strong>{row.team_name}{following.includes(row.team_abbrev) && <FavoriteStar />}</strong>
                <small>{row.wins}-{row.losses}-{row.ot_losses} · L10 {row.l10_wins}-{row.l10_losses}-{row.l10_ot_losses}{streak}</small>
              </span>
              <span className={odds != null && Number(odds) >= 0.5 ? "standings-row-po po-in" : "standings-row-po"}>
                <strong>{formatOdds(odds)}</strong><small>PO%</small>
              </span>
              <span className="standings-row-pts"><strong>{row.points}</strong><small>PTS</small></span>
            </button>
          </Fragment>
        );
      })}
    </div>
    </>
  );
}

export default StandingsTable;
