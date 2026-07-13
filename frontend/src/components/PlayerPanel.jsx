const POSITION_LABELS = { C: "Center", L: "Left Wing", R: "Right Wing", D: "Defenseman", G: "Goalie" };

function CareerStatTiles({ stats, isGoalie }) {
  return (
    <div className="stat-tiles">
      {isGoalie ? (
        <>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.wins}-{stats.losses}-{stats.ot_losses}</span>
            <span className="stat-tile-label">RECORD</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">
              {stats.goals_against_avg != null ? Number(stats.goals_against_avg).toFixed(2) : "—"}
            </span>
            <span className="stat-tile-label">GAA</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">
              {stats.save_pctg != null ? Number(stats.save_pctg).toFixed(3) : "—"}
            </span>
            <span className="stat-tile-label">SV%</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.shutouts ?? "—"}</span>
            <span className="stat-tile-label">SO</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.games_played ?? "—"}</span>
            <span className="stat-tile-label">GP</span>
          </div>
        </>
      ) : (
        <>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.points ?? "—"}</span>
            <span className="stat-tile-label">POINTS</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.goals ?? "—"}</span>
            <span className="stat-tile-label">GOALS</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.assists ?? "—"}</span>
            <span className="stat-tile-label">ASSISTS</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.plus_minus ?? "—"}</span>
            <span className="stat-tile-label">+/-</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.shots ?? "—"}</span>
            <span className="stat-tile-label">SHOTS</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.pim ?? "—"}</span>
            <span className="stat-tile-label">PIM</span>
          </div>
          <div className="stat-tile">
            <span className="stat-tile-value">{stats.games_played ?? "—"}</span>
            <span className="stat-tile-label">GP</span>
          </div>
        </>
      )}
    </div>
  );
}

function PlayerPanel({ player, onBack, backLabel }) {
  if (!player) return null;

  const isGoalie = player.position_code === "G";
  const seasonStats = player.season_stats?.[0];
  const advancedStats = player.advanced_stats?.[0];
  const careerRegularSeason = player.career_totals?.regular_season ?? null;
  const careerPlayoffs = player.career_totals?.playoffs ?? null;
  const hasCareerTotals = careerRegularSeason != null || careerPlayoffs != null;
  const heightLabel = player.height_in_inches
    ? `${Math.floor(player.height_in_inches / 12)}'${player.height_in_inches % 12}"`
    : "—";

  return (
    <div className="player-panel">
      <button className="back-link" onClick={onBack}>&larr; {backLabel}</button>

      <div className="player-header">
        {player.headshot_url && <img className="player-headshot" src={player.headshot_url} alt="" />}
        <div>
          <div className="player-name">{player.first_name} {player.last_name}</div>
          <div className="player-sub">
            {player.team_logo_url && <img className="player-team-logo" src={player.team_logo_url} alt="" />}
            #{player.sweater_number ?? "—"} &middot; {POSITION_LABELS[player.position_code] ?? player.position_code}
          </div>
        </div>
      </div>

      <div className="player-bio">
        <div className="bio-item">
          <span className="bio-label">SHOOTS/CATCHES</span>
          <span className="bio-value">{player.shoots_catches ?? "—"}</span>
        </div>
        <div className="bio-item">
          <span className="bio-label">HEIGHT</span>
          <span className="bio-value">{heightLabel}</span>
        </div>
        <div className="bio-item">
          <span className="bio-label">WEIGHT</span>
          <span className="bio-value">{player.weight_in_pounds ? `${player.weight_in_pounds} lbs` : "—"}</span>
        </div>
        <div className="bio-item">
          <span className="bio-label">BORN</span>
          <span className="bio-value">{player.birth_date ?? "—"}</span>
        </div>
        <div className="bio-item">
          <span className="bio-label">HOMETOWN</span>
          <span className="bio-value">
            {player.birth_city ? `${player.birth_city}, ${player.birth_country}` : "—"}
          </span>
        </div>
      </div>

      {seasonStats && (
        <div className="stat-tiles">
          {isGoalie ? (
            <>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.wins}-{seasonStats.losses}-{seasonStats.ot_losses}</span>
                <span className="stat-tile-label">RECORD</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">
                  {seasonStats.goals_against_avg != null ? Number(seasonStats.goals_against_avg).toFixed(2) : "—"}
                </span>
                <span className="stat-tile-label">GAA</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">
                  {seasonStats.save_pctg != null ? Number(seasonStats.save_pctg).toFixed(3) : "—"}
                </span>
                <span className="stat-tile-label">SV%</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.shutouts ?? "—"}</span>
                <span className="stat-tile-label">SO</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.games_played ?? "—"}</span>
                <span className="stat-tile-label">GP</span>
              </div>
            </>
          ) : (
            <>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.points ?? "—"}</span>
                <span className="stat-tile-label">POINTS</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.goals ?? "—"}</span>
                <span className="stat-tile-label">GOALS</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.assists ?? "—"}</span>
                <span className="stat-tile-label">ASSISTS</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.plus_minus ?? "—"}</span>
                <span className="stat-tile-label">+/-</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.shots ?? "—"}</span>
                <span className="stat-tile-label">SHOTS</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.pim ?? "—"}</span>
                <span className="stat-tile-label">PIM</span>
              </div>
              <div className="stat-tile">
                <span className="stat-tile-value">{seasonStats.games_played ?? "—"}</span>
                <span className="stat-tile-label">GP</span>
              </div>
            </>
          )}
        </div>
      )}

      {!isGoalie && advancedStats && (
        <div className="advanced-stats-panel">
          <div className="trend-eyebrow advanced-stats-header">ADVANCED (5-ON-5)</div>
          <div className="stat-tiles">
            <div className="stat-tile">
              <span className="stat-tile-value">
                {advancedStats.corsi_for_pct != null ? `${(Number(advancedStats.corsi_for_pct) * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="stat-tile-label">CORSI FOR %</span>
            </div>
            <div className="stat-tile">
              <span className="stat-tile-value">{advancedStats.corsi_for}-{advancedStats.corsi_against}</span>
              <span className="stat-tile-label">CF - CA</span>
            </div>
            <div className="stat-tile">
              <span className="stat-tile-value">
                {advancedStats.fenwick_for_pct != null ? `${(Number(advancedStats.fenwick_for_pct) * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="stat-tile-label">FENWICK FOR %</span>
            </div>
            <div className="stat-tile">
              <span className="stat-tile-value">{advancedStats.fenwick_for}-{advancedStats.fenwick_against}</span>
              <span className="stat-tile-label">FF - FA</span>
            </div>
          </div>
          {seasonStats && advancedStats.games_processed < seasonStats.games_played && (
            <div className="advanced-stats-caveat">
              Based on shift data from {advancedStats.games_processed} of {seasonStats.games_played} games played
              this season &mdash; computed from official NHL play-by-play and shift data (the NHL's own shift-chart
              data isn't complete for every game).
            </div>
          )}
        </div>
      )}

      {hasCareerTotals && (
        <div className="advanced-stats-panel">
          <div className="trend-eyebrow advanced-stats-header">CAREER TOTALS</div>
          {careerRegularSeason && (
            <>
              <div className="career-totals-subheader">Regular Season</div>
              <CareerStatTiles stats={careerRegularSeason} isGoalie={isGoalie} />
            </>
          )}
          {careerPlayoffs && (
            <>
              <div className="career-totals-subheader">Playoffs</div>
              <CareerStatTiles stats={careerPlayoffs} isGoalie={isGoalie} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default PlayerPanel;
