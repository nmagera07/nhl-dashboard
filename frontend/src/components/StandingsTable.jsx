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
      {value.toFixed(0)}%
    </td>
  );
}

function StandingsTable({ rows, selectedTeam, onSelectTeam, playoffOddsByTeam }) {
  return (
    <div className="table-card">
      <table className="standings-table">
        <thead>
          <tr>
            <th className="col-rank"></th>
            <th className="col-team">TEAM</th>
            <th>GP</th>
            <th>W</th>
            <th>L</th>
            <th>OT</th>
            <th className="col-pts">PTS</th>
            <th>GF</th>
            <th>GA</th>
            <th>DIFF</th>
            <th>L10</th>
            <th>STRK</th>
            <th className="col-po">PO%</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={12} className="no-results">No teams match your search.</td>
            </tr>
          )}
          {rows
            .sort((a, b) => a.division_sequence - b.division_sequence)
            .map((row) => (
              <tr
                key={row.team_abbrev}
                className={row.team_abbrev === selectedTeam ? "row-selected" : ""}
                onClick={() => onSelectTeam(row.team_abbrev)}
              >
                <td className="col-rank">{row.division_sequence}</td>
                <td className="col-team">
                  <span className="team-abbrev">{row.team_abbrev}</span>
                  <span className="team-name">{row.team_name}</span>
                </td>
                <td>{row.games_played}</td>
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
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

export default StandingsTable;
