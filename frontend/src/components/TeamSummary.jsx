import { darkLogo } from "../utils/darkLogo.js";

// Header of the team page: identity, playoff status, and the season at a
// glance. Replaces the old TeamCard that sat under the standings table.

function isInPlayoffSpot(team) {
  return team.division_sequence <= 3 || (team.wildcard_sequence != null && team.wildcard_sequence <= 2);
}

function formatPointPct(value) {
  return value != null ? `${(Number(value) * 100).toFixed(1)}%` : "—";
}

function TeamSummary({ team }) {
  if (!team) return null;

  const inPlayoffs = isInPlayoffSpot(team);
  const diff = team.goal_differential;
  const stats = [
    { label: "PTS", value: team.points, highlight: true },
    { label: "Record", value: `${team.wins}-${team.losses}-${team.ot_losses}` },
    { label: "Point %", value: formatPointPct(team.point_pctg) },
    { label: "Diff", value: diff == null ? "—" : `${diff > 0 ? "+" : ""}${diff}`, tone: diff > 0 ? "pos" : diff < 0 ? "neg" : null },
    { label: "Last 10", value: `${team.l10_wins}-${team.l10_losses}-${team.l10_ot_losses}` },
    { label: "Streak", value: team.streak_code ? `${team.streak_code}${team.streak_count}` : "—" },
    { label: "Home", value: `${team.home_wins}-${team.home_losses}` },
    { label: "Road", value: `${team.road_wins}-${team.road_losses}` },
  ];

  return (
    <section className="team-summary" aria-label={`${team.team_name} season summary`}>
      <div className="team-summary-identity">
        {team.logo_url && <img className="team-summary-logo" src={darkLogo(team.logo_url)} alt="" />}
        <div className="team-summary-title">
          <h1>{team.team_name}</h1>
          <p>
            {team.division} Division · #{team.division_sequence} div · #{team.conference_sequence} conf · #{team.league_sequence} NHL
          </p>
        </div>
        <span className={inPlayoffs ? "playoff-badge playoff-in" : "playoff-badge playoff-out"}>
          {inPlayoffs ? "In playoff spot" : "Outside looking in"}
        </span>
      </div>
      <dl className="team-summary-stats">
        {stats.map((stat) => (
          <div key={stat.label} className="team-summary-stat">
            <dt>{stat.label}</dt>
            <dd className={[stat.highlight && "is-highlight", stat.tone && `is-${stat.tone}`].filter(Boolean).join(" ") || undefined}>
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default TeamSummary;
