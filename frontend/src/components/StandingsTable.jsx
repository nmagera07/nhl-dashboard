import { darkLogo } from "../utils/darkLogo.js";
import { formatOdds } from "../utils/playoffRace.js";

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

function TeamCell({ row }) {
  return (
    <td className="col-team">
      <span className="team-cell">
        {row.logo_url ? <img className="team-cell-logo" src={darkLogo(row.logo_url)} alt="" /> : <span className="team-cell-logo" />}
        <span className="team-abbrev">{row.team_abbrev}</span>
        <span className="team-name">{row.team_name}</span>
      </span>
    </td>
  );
}

function StandingsTable({ rows, onSelectTeam, playoffOddsByTeam, sortBy, sortDir, onSort, view = "standard" }) {
  // Rows arrive already ordered by the API when a column sort is active
  // (?sort_by=... on GET /standings/latest) -- only fall back to the
  // default division-rank ordering when no custom sort is in effect.
  // Copy before sorting so this never mutates the rows prop in place.
  const displayRows = sortBy ? rows : [...rows].sort((a, b) => a.division_sequence - b.division_sequence);
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
            <th>GP</th>
            {advanced ? (
              <>
                <th className="col-pts">PTS</th>
                {ADVANCED_SORT_COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={col.key === sortBy ? "sortable-col sortable-col-active" : "sortable-col"}
                    onClick={() => onSort(col.key)}
                  >
                    {col.label}{col.key === sortBy ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </th>
                ))}
              </>
            ) : (
              <>
                <th>W</th>
                <th>L</th>
                <th>OT</th>
                <th className="col-pts">PTS</th>
                <th>GF</th>
                <th>GA</th>
                <th>DIFF</th>
                <th>L10</th>
                <th>STRK</th>
                <th className="col-po" title="Playoff odds from a daily Monte Carlo simulation">PO%</th>
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
          {displayRows.map((row) => (
            <tr key={row.team_abbrev} onClick={() => onSelectTeam(row.team_abbrev)}>
              <td className="col-rank">{row.division_sequence}</td>
              <TeamCell row={row} />
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
    <div className="standings-mobile-list" aria-label="Team standings cards">
      {displayRows.length === 0 && <div className="standings-mobile-empty">No teams match your search.</div>}
      {displayRows.map((row) => (
        <button
          className="standings-team-card"
          key={row.team_abbrev}
          type="button"
          aria-label={`Open ${row.team_name} team page`}
          onClick={() => onSelectTeam(row.team_abbrev)}
        >
          <span className="standings-team-card-header">
            <span className="standings-team-rank">{row.division_sequence}</span>
            {row.logo_url && <img className="standings-team-logo" src={darkLogo(row.logo_url)} alt="" />}
            <span className="standings-team-identity"><strong>{row.team_name}</strong><small>{row.wins}-{row.losses}-{row.ot_losses} · {row.games_played} GP</small></span>
            <span className="standings-team-points"><strong>{row.points}</strong><small>PTS</small></span>
          </span>
          <span className="standings-team-card-stats">
            <span><strong>{row.goal_for}-{row.goal_against}</strong><small>GF-GA</small></span>
            <span><strong>{row.goal_differential > 0 ? "+" : ""}{row.goal_differential}</strong><small>DIFF</small></span>
            <span><strong>{row.l10_wins}-{row.l10_losses}-{row.l10_ot_losses}</strong><small>L10</small></span>
            <span><strong>{row.streak_code ? `${row.streak_code}${row.streak_count}` : "—"}</strong><small>STRK</small></span>
            <span><strong>{formatOdds(playoffOddsByTeam?.[row.team_abbrev])}</strong><small>PO%</small></span>
          </span>
        </button>
      ))}
    </div>
    </>
  );
}

export default StandingsTable;
