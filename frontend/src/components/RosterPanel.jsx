function SkaterTable({ label, players, onSelectPlayer }) {
  if (players.length === 0) return null;
  return (
    <>
      <div className="roster-section-label">{label}</div>
      <div className="table-card roster-section">
        <table className="standings-table">
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th className="col-team">PLAYER</th>
              <th>GP</th>
              <th>G</th>
              <th>A</th>
              <th className="col-pts">PTS</th>
              <th>+/-</th>
              <th>PIM</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{p.sweater_number ?? "—"}</td>
                <td className="col-team">
                  {p.headshot_url && <img className="player-thumb" src={p.headshot_url} alt="" />}
                  <span className="player-name-cell">{p.first_name} {p.last_name}</span>
                </td>
                <td>{p.games_played ?? "—"}</td>
                <td>{p.goals ?? "—"}</td>
                <td>{p.assists ?? "—"}</td>
                <td className="col-pts">{p.points ?? "—"}</td>
                <td>{p.plus_minus ?? "—"}</td>
                <td>{p.pim ?? "—"}</td>
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
      <div className="roster-section-label">Goalies</div>
      <div className="table-card roster-section">
        <table className="standings-table">
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th className="col-team">PLAYER</th>
              <th>GP</th>
              <th>W</th>
              <th>L</th>
              <th>OTL</th>
              <th>GAA</th>
              <th>SV%</th>
              <th>SO</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{p.sweater_number ?? "—"}</td>
                <td className="col-team">
                  {p.headshot_url && <img className="player-thumb" src={p.headshot_url} alt="" />}
                  <span className="player-name-cell">{p.first_name} {p.last_name}</span>
                </td>
                <td>{p.games_played ?? "—"}</td>
                <td>{p.wins ?? "—"}</td>
                <td>{p.losses ?? "—"}</td>
                <td>{p.ot_losses ?? "—"}</td>
                <td>{p.goals_against_avg != null ? Number(p.goals_against_avg).toFixed(2) : "—"}</td>
                <td>{p.save_pctg != null ? Number(p.save_pctg).toFixed(3) : "—"}</td>
                <td>{p.shutouts ?? "—"}</td>
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
    <div className="roster-panel">
      <button className="back-link" onClick={onBack}>&larr; Back to Standings</button>

      {team && (
        <div className="roster-header">
          {team.logo_url && <img className="team-logo-lg" src={team.logo_url} alt="" />}
          <div>
            <div className="roster-team-name">{team.team_name}</div>
            <div className="roster-team-sub">Roster</div>
          </div>
        </div>
      )}

      <SkaterTable label="Forwards" players={forwards} onSelectPlayer={onSelectPlayer} />
      <SkaterTable label="Defensemen" players={defensemen} onSelectPlayer={onSelectPlayer} />
      <GoalieTable players={goalies} onSelectPlayer={onSelectPlayer} />
    </div>
  );
}

export default RosterPanel;
