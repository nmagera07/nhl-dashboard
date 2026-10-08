import TeamSummary from "./TeamSummary.jsx";

// Columns marked col-optional hide on phones so the table fits without
// sideways scrolling; the essentials stay.

function PlayerCell({ p }) {
  return (
    <td className="col-team">
      <span className="roster-player">
        {p.headshot_url ? <img className="player-thumb" src={p.headshot_url} alt="" /> : <span className="player-thumb" />}
        <span className="player-name-cell" title={`${p.first_name} ${p.last_name}`}>{p.first_name} {p.last_name}</span>
      </span>
    </td>
  );
}

function SectionLabel({ label, count }) {
  return (
    <h2 className="roster-section-label">
      {label} <span className="roster-section-count">{count}</span>
    </h2>
  );
}

function SkaterTable({ label, players, onSelectPlayer }) {
  if (players.length === 0) return null;
  return (
    <>
      <SectionLabel label={label} count={players.length} />
      <div className="table-card roster-section">
        <table className="standings-table roster-table" aria-label={label}>
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th className="col-team">PLAYER</th>
              <th>GP</th>
              <th>G</th>
              <th>A</th>
              <th className="col-pts">PTS</th>
              <th>+/-</th>
              <th className="col-optional">SOG</th>
              <th className="col-optional">PIM</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{p.sweater_number ?? "—"}</td>
                <PlayerCell p={p} />
                <td>{p.games_played ?? "—"}</td>
                <td>{p.goals ?? "—"}</td>
                <td>{p.assists ?? "—"}</td>
                <td className="col-pts">{p.points ?? "—"}</td>
                <td>{p.plus_minus == null ? "—" : `${p.plus_minus > 0 ? "+" : ""}${p.plus_minus}`}</td>
                <td className="col-optional">{p.shots ?? "—"}</td>
                <td className="col-optional">{p.pim ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function GoalieTable({ players, onSelectPlayer }) {
  if (players.length === 0) return null;
  return (
    <>
      <SectionLabel label="Goalies" count={players.length} />
      <div className="table-card roster-section">
        <table className="standings-table roster-table" aria-label="Goalies">
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th className="col-team">PLAYER</th>
              <th>GP</th>
              <th>W</th>
              <th>L</th>
              <th className="col-optional">OTL</th>
              <th>GAA</th>
              <th className="col-pts">SV%</th>
              <th className="col-optional">SO</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{p.sweater_number ?? "—"}</td>
                <PlayerCell p={p} />
                <td>{p.games_played ?? "—"}</td>
                <td>{p.wins ?? "—"}</td>
                <td>{p.losses ?? "—"}</td>
                <td className="col-optional">{p.ot_losses ?? "—"}</td>
                <td>{p.goals_against_avg != null ? Number(p.goals_against_avg).toFixed(2) : "—"}</td>
                <td className="col-pts">{p.save_pctg != null ? Number(p.save_pctg).toFixed(3).replace(/^0/, "") : "—"}</td>
                <td className="col-optional">{p.shutouts ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function RosterPanel({ team, roster, onSelectPlayer, onBack }) {
  const forwards = roster.filter((p) => ["C", "L", "R"].includes(p.position_code));
  const defensemen = roster.filter((p) => p.position_code === "D");
  const goalies = roster.filter((p) => p.position_code === "G");

  return (
    <main className="roster-panel">
      <button className="back-link" onClick={onBack}>&larr; Standings</button>
      <TeamSummary team={team} />
      <SkaterTable label="Forwards" players={forwards} onSelectPlayer={onSelectPlayer} />
      <SkaterTable label="Defense" players={defensemen} onSelectPlayer={onSelectPlayer} />
      <GoalieTable players={goalies} onSelectPlayer={onSelectPlayer} />
    </main>
  );
}

export default RosterPanel;
