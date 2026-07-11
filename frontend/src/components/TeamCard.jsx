function TeamCard({ team, onViewRoster }) {
  if (!team) return null;

  const pointPct = team.point_pctg != null ? `${(Number(team.point_pctg) * 100).toFixed(1)}%` : "—";
  const inPlayoffs = team.division_sequence <= 3 || (team.wildcard_sequence != null && team.wildcard_sequence <= 2);

  return (
    <div className="team-card">
      <div className="team-card-header">
        {team.logo_url && <img className="team-logo" src={team.logo_url} alt="" />}
        <div>
          <div className="team-card-name">{team.team_name}</div>
          <div className="team-card-division">{team.division} Division</div>
        </div>
      </div>

      <div className={inPlayoffs ? "playoff-badge playoff-in" : "playoff-badge playoff-out"}>
        {inPlayoffs ? "IN PLAYOFF SPOT" : "OUTSIDE LOOKING IN"}
      </div>

      <div className="team-card-record">
        <span className="team-card-pts">{team.points} PTS</span>
        <span className="team-card-sub">{team.wins}-{team.losses}-{team.ot_losses} &middot; {pointPct}</span>
      </div>

      <div className="team-card-splits">
        <div className="split">
          <span className="split-label">HOME</span>
          <span className="split-value">{team.home_wins}-{team.home_losses}</span>
        </div>
        <div className="split">
          <span className="split-label">ROAD</span>
          <span className="split-value">{team.road_wins}-{team.road_losses}</span>
        </div>
        <div className="split">
          <span className="split-label">L10</span>
          <span className="split-value">{team.l10_wins}-{team.l10_losses}-{team.l10_ot_losses}</span>
        </div>
      </div>

      <div className="team-card-ranks">
        <div className="rank-item">
          <span className="rank-value">#{team.division_sequence}</span>
          <span className="rank-label">Division</span>
        </div>
        <div className="rank-item">
          <span className="rank-value">#{team.conference_sequence}</span>
          <span className="rank-label">Conference</span>
        </div>
        <div className="rank-item">
          <span className="rank-value">#{team.league_sequence}</span>
          <span className="rank-label">League</span>
        </div>
      </div>

      <button className="roster-link" onClick={() => onViewRoster(team.team_abbrev)}>
        View Roster →
      </button>
    </div>
  );
}

export default TeamCard;
