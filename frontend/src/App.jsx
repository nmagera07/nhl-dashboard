import { useState, useEffect, useMemo } from "react";
import {
  Routes, Route, Navigate, useNavigate, useLocation, useParams,
} from "react-router-dom";
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList,
} from "recharts";

// Points at the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, swap this
// back to "http://127.0.0.1:8000".
const API_BASE = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";

const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];

function StreakBadge({ code, count }) {
  if (!code) return <span className="streak streak-none">—</span>;
  const cls = code === "W" ? "streak streak-w" : code === "L" ? "streak streak-l" : "streak streak-ot";
  return <span className={cls}>{code}{count}</span>;
}

function TopNav({ section, onNavigate, search, onSearchChange }) {
  return (
    <div className="topnav">
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">NHL Standings</span>
      </div>
      <div className="nav-tabs">
        <button
          className={section === "standings" ? "nav-tab nav-tab-active" : "nav-tab"}
          onClick={() => onNavigate("standings")}
        >
          Standings
        </button>
        <button
          className={section === "players" ? "nav-tab nav-tab-active" : "nav-tab"}
          onClick={() => onNavigate("players")}
        >
          Player Stats
        </button>
      </div>
      <div className="nav-right">
        {section === "standings" && (
          <input
            className="search-input"
            placeholder="Find a team..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        )}
        <span className="live-badge">
          <span className="live-dot" /> LIVE
        </span>
      </div>
    </div>
  );
}

function DivisionTabs({ divisions, active, onSelect, disabled }) {
  return (
    <div className={disabled ? "division-tabs division-tabs-disabled" : "division-tabs"}>
      {divisions.map((div) => (
        <button
          key={div}
          className={div === active ? "division-tab division-tab-active" : "division-tab"}
          onClick={() => onSelect(div)}
          disabled={disabled}
        >
          {div.toUpperCase()}
        </button>
      ))}
    </div>
  );
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

function formatSeasonLabel(seasonId) {
  const str = String(seasonId);
  return `${str.slice(2, 4)}-${str.slice(6, 8)}`;
}

function YearlyDot({ cx, cy, payload }) {
  const fill = payload?.madePlayoffs ? "#3b82f6" : "#4b5563";
  return <circle cx={cx} cy={cy} r={5} fill={fill} stroke="#0a0b0f" strokeWidth={2} />;
}

function YearlyPointLabel({ x, y, value }) {
  return (
    <text x={x} y={y - 14} textAnchor="middle" fill="#e5e7eb" fontSize={12} fontWeight={700}>
      {value}
    </text>
  );
}

const chartTooltipStyle = {
  contentStyle: {
    background: "#12151c",
    border: "1px solid #1f2937",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "#e5e7eb" },
};

function TrendChart({ mode, onModeChange, history, seasonHistory, teamAbbrev }) {
  const dailyData = history.map((h) => ({
    date: h.snapshot_date,
    points: h.points,
  }));

  const yearlyData = seasonHistory.map((s) => ({
    season: formatSeasonLabel(s.season_id),
    points: s.points,
    madePlayoffs: s.made_playoffs,
  }));

  return (
    <div className="trend-panel">
      <div className="trend-header">
        <span className="trend-eyebrow">{mode === "years" ? "LAST 5 YEARS" : "SEASON TREND"}</span>
        <span className="trend-team">{teamAbbrev}</span>
        <div className="trend-toggle">
          <button
            className={mode === "season" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
            onClick={() => onModeChange("season")}
          >
            This Season
          </button>
          <button
            className={mode === "years" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
            onClick={() => onModeChange("years")}
          >
            Last 5 Years
          </button>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        {mode === "years" ? (
          <AreaChart data={yearlyData} margin={{ top: 24, right: 20, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="yearlyFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="season" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
            <Tooltip {...chartTooltipStyle} />
            <Area
              type="monotone"
              dataKey="points"
              stroke="#3b82f6"
              strokeWidth={2.5}
              fill="url(#yearlyFill)"
              dot={<YearlyDot />}
              isAnimationActive={false}
            >
              <LabelList dataKey="points" content={<YearlyPointLabel />} />
            </Area>
          </AreaChart>
        ) : (
          <LineChart data={dailyData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
            <Tooltip {...chartTooltipStyle} />
            <Line type="monotone" dataKey="points" stroke="#3b82f6" strokeWidth={2.5} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
      {mode === "years" && (
        <div className="years-legend">
          <span><span className="legend-dot legend-dot-playoff" /> Made playoffs</span>
          <span><span className="legend-dot legend-dot-missed" /> Missed playoffs</span>
        </div>
      )}
    </div>
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

const POSITION_LABELS = { C: "Center", L: "Left Wing", R: "Right Wing", D: "Defenseman", G: "Goalie" };

function PlayerPanel({ player, onBack, backLabel }) {
  if (!player) return null;

  const isGoalie = player.position_code === "G";
  const seasonStats = player.season_stats?.[0];
  const advancedStats = player.advanced_stats?.[0];
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
    </div>
  );
}

const SKATER_COLUMNS = [
  { key: "points", label: "PTS" },
  { key: "goals", label: "G" },
  { key: "assists", label: "A" },
  { key: "plus_minus", label: "+/-" },
  { key: "pim", label: "PIM" },
  { key: "shots", label: "SHOTS" },
  { key: "games_played", label: "GP" },
];

const GOALIE_COLUMNS = [
  { key: "wins", label: "W" },
  { key: "losses", label: "L" },
  { key: "ot_losses", label: "OTL" },
  { key: "goals_against_avg", label: "GAA" },
  { key: "save_pctg", label: "SV%" },
  { key: "shutouts", label: "SO" },
  { key: "games_played", label: "GP" },
];

const LOWER_IS_BETTER = new Set(["goals_against_avg", "losses", "ot_losses", "pim"]);
const LEADERBOARD_PAGE_SIZE = 50;

function formatStatValue(key, value) {
  if (value == null) return "—";
  if (key === "goals_against_avg") return Number(value).toFixed(2);
  if (key === "save_pctg") return Number(value).toFixed(3);
  return value;
}

function LeaderboardPanel({ players, onSelectPlayer }) {
  const [group, setGroup] = useState("skaters"); // skaters | goalies
  const [sortKey, setSortKey] = useState("points");
  const [sortDir, setSortDir] = useState("desc");
  const [search, setSearch] = useState("");

  const columns = group === "goalies" ? GOALIE_COLUMNS : SKATER_COLUMNS;

  const handleGroupChange = (nextGroup) => {
    setGroup(nextGroup);
    setSortKey(nextGroup === "goalies" ? "wins" : "points");
    setSortDir("desc");
  };

  const handleSort = (key) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(LOWER_IS_BETTER.has(key) ? "asc" : "desc");
    }
  };

  const isSearching = search.trim().length > 0;

  const groupPlayers = useMemo(
    () => players.filter((p) => (group === "goalies" ? p.position_code === "G" : p.position_code !== "G")),
    [players, group]
  );

  const filtered = useMemo(() => {
    if (!isSearching) return groupPlayers;
    const q = search.trim().toLowerCase();
    return groupPlayers.filter(
      (p) =>
        `${p.first_name} ${p.last_name}`.toLowerCase().includes(q) ||
        p.team_abbrev.toLowerCase().includes(q)
    );
  }, [groupPlayers, search, isSearching]);

  const sorted = useMemo(() => {
    const withRank = [...filtered].sort((a, b) => {
      const av = a[sortKey] ?? (sortDir === "asc" ? Infinity : -Infinity);
      const bv = b[sortKey] ?? (sortDir === "asc" ? Infinity : -Infinity);
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return withRank;
  }, [filtered, sortKey, sortDir]);

  const displayed = isSearching ? sorted : sorted.slice(0, LEADERBOARD_PAGE_SIZE);

  return (
    <div className="leaderboard-panel">
      <div className="leaderboard-controls">
        <div className="leaderboard-group-tabs">
          <button
            className={group === "skaters" ? "division-tab division-tab-active" : "division-tab"}
            onClick={() => handleGroupChange("skaters")}
          >
            SKATERS
          </button>
          <button
            className={group === "goalies" ? "division-tab division-tab-active" : "division-tab"}
            onClick={() => handleGroupChange("goalies")}
          >
            GOALIES
          </button>
        </div>
        <input
          className="search-input leaderboard-search"
          placeholder="Find a player..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="status-line">
        {isSearching
          ? `${sorted.length} result${sorted.length === 1 ? "" : "s"} for "${search.trim()}"`
          : `Showing top ${Math.min(LEADERBOARD_PAGE_SIZE, sorted.length)} of ${sorted.length}`}
      </div>

      <div className="table-card leaderboard-table-card">
        <table className="standings-table">
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th className="col-team">PLAYER</th>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={col.key === sortKey ? "sortable-col sortable-col-active" : "sortable-col"}
                  onClick={() => handleSort(col.key)}
                >
                  {col.label}{col.key === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.length === 0 && (
              <tr>
                <td colSpan={2 + columns.length} className="no-results">No players match your search.</td>
              </tr>
            )}
            {displayed.map((p, i) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{i + 1}</td>
                <td className="col-team">
                  {p.team_logo_url && <img className="leaderboard-team-logo" src={p.team_logo_url} alt="" />}
                  <span className="team-abbrev">{p.team_abbrev}</span>
                  <span className="team-name">{p.first_name} {p.last_name}</span>
                </td>
                {columns.map((col) => (
                  <td key={col.key} className={col.key === sortKey ? "col-pts" : ""}>
                    {formatStatValue(col.key, p[col.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StandingsPage({
  divisions,
  activeDivision,
  onSelectDivision,
  isSearching,
  visibleRows,
  selectedTeam,
  onSelectTeam,
  playoffOddsByTeam,
  playoffOddsStatus,
  selectedRow,
  history,
  seasonHistory,
  trendMode,
  onTrendModeChange,
  onViewRoster,
}) {
  return (
    <>
      <DivisionTabs
        divisions={divisions}
        active={activeDivision}
        onSelect={onSelectDivision}
        disabled={isSearching}
      />
      <StandingsTable
        rows={visibleRows}
        selectedTeam={selectedTeam}
        onSelectTeam={onSelectTeam}
        playoffOddsByTeam={playoffOddsByTeam}
      />
      {playoffOddsStatus === "error" && (
        <div className="status-line status-error">
          Playoff odds unavailable — the PO% column may be incomplete.
        </div>
      )}
      {history.length > 0 && (
        <div className="detail-grid">
          <TeamCard team={selectedRow} onViewRoster={onViewRoster} />
          <TrendChart
            mode={trendMode}
            onModeChange={onTrendModeChange}
            history={history}
            seasonHistory={seasonHistory}
            teamAbbrev={selectedTeam}
          />
        </div>
      )}
    </>
  );
}

function RosterPage({ standings }) {
  const { teamAbbrev } = useParams();
  const navigate = useNavigate();
  const abbrev = teamAbbrev?.toUpperCase();

  const [roster, setRoster] = useState([]);
  const [rosterStatus, setRosterStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    fetch(`${API_BASE}/teams/${abbrev}/roster`)
      .then((res) => res.json())
      .then((data) => {
        setRoster(Array.isArray(data) ? data : []);
        setRosterStatus("ready");
      })
      .catch(() => setRosterStatus("error"));
  }, [abbrev]);

  const team = useMemo(
    () => standings.find((r) => r.team_abbrev === abbrev),
    [standings, abbrev]
  );

  const handleSelectPlayer = (playerId) => {
    navigate(`/players/${playerId}`, { state: { from: "roster", teamAbbrev: abbrev } });
  };

  return (
    <>
      {rosterStatus === "loading" && <div className="status-line">Loading roster…</div>}
      {rosterStatus === "error" && (
        <div className="status-line status-error">Couldn't load the roster.</div>
      )}
      {rosterStatus === "ready" && (
        <RosterPanel
          team={team}
          roster={roster}
          onSelectPlayer={handleSelectPlayer}
          onBack={() => navigate("/")}
        />
      )}
    </>
  );
}

function PlayerPage() {
  const { playerId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [playerDetail, setPlayerDetail] = useState(null);
  const [playerStatus, setPlayerStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    fetch(`${API_BASE}/players/${playerId}`)
      .then((res) => res.json())
      .then((data) => {
        setPlayerDetail(data);
        setPlayerStatus("ready");
      })
      .catch(() => setPlayerStatus("error"));
  }, [playerId]);

  // Prefer the explicit "where did you come from" state passed at navigation
  // time; a direct deep link (no state) falls back to the player's own team
  // roster, which is always a sensible destination and doesn't depend on
  // browser history existing at all.
  const cameFromLeaderboard = location.state?.from === "leaderboard";
  const backLabel = cameFromLeaderboard ? "Back to Leaderboard" : "Back to Roster";
  const handleBack = () => {
    if (cameFromLeaderboard) navigate("/leaderboard");
    else navigate(playerDetail?.team_abbrev ? `/teams/${playerDetail.team_abbrev}` : "/");
  };

  return (
    <>
      {playerStatus === "loading" && <div className="status-line">Loading player…</div>}
      {playerStatus === "error" && (
        <div className="status-line status-error">Couldn't load player details.</div>
      )}
      {playerStatus === "ready" && (
        <PlayerPanel player={playerDetail} onBack={handleBack} backLabel={backLabel} />
      )}
    </>
  );
}

function LeaderboardPage() {
  const navigate = useNavigate();
  const [leaders, setLeaders] = useState([]);
  const [leadersStatus, setLeadersStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    fetch(`${API_BASE}/players/leaders`)
      .then((res) => res.json())
      .then((data) => {
        setLeaders(Array.isArray(data) ? data : []);
        setLeadersStatus("ready");
      })
      .catch(() => setLeadersStatus("error"));
  }, []);

  const handleSelectPlayer = (playerId) => {
    navigate(`/players/${playerId}`, { state: { from: "leaderboard" } });
  };

  return (
    <>
      {leadersStatus === "loading" && <div className="status-line">Loading players…</div>}
      {leadersStatus === "error" && (
        <div className="status-line status-error">Couldn't load player stats.</div>
      )}
      {leadersStatus === "ready" && (
        <LeaderboardPanel players={leaders} onSelectPlayer={handleSelectPlayer} />
      )}
    </>
  );
}

export default function NHLDashboard() {
  const [standings, setStandings] = useState([]);
  const [history, setHistory] = useState([]);
  const [seasonHistory, setSeasonHistory] = useState([]);
  const [trendMode, setTrendMode] = useState("season"); // season | years
  const [selectedTeam, setSelectedTeam] = useState("PIT");
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [activeDivision, setActiveDivision] = useState(null);
  const [search, setSearch] = useState("");
  const [playoffOdds, setPlayoffOdds] = useState([]);
  const [playoffOddsStatus, setPlayoffOddsStatus] = useState("loading"); // loading | ready | error

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    fetch(`${API_BASE}/standings/latest`)
      .then((res) => res.json())
      .then((data) => {
        setStandings(data);
        setStatus("ready");
        const firstDivision = data.find((d) => d.division)?.division;
        if (firstDivision) setActiveDivision(firstDivision);
      })
      .catch(() => setStatus("error"));

    fetch(`${API_BASE}/playoff-odds`)
      .then((res) => res.json())
      .then((data) => {
        setPlayoffOdds(Array.isArray(data) ? data : []);
        setPlayoffOddsStatus("ready");
      })
      .catch(() => setPlayoffOddsStatus("error"));
  }, []);

  useEffect(() => {
    if (!selectedTeam) return;
    fetch(`${API_BASE}/standings/${selectedTeam}`)
      .then((res) => res.json())
      .then((data) => setHistory(Array.isArray(data) ? data : []))
      .catch(() => setHistory([]));
    fetch(`${API_BASE}/standings/${selectedTeam}/seasons`)
      .then((res) => res.json())
      .then((data) => setSeasonHistory(Array.isArray(data) ? data : []))
      .catch(() => setSeasonHistory([]));
  }, [selectedTeam]);

  const handleViewRoster = (teamAbbrev) => navigate(`/teams/${teamAbbrev}`);

  const handleNavigate = (section) => navigate(section === "players" ? "/leaderboard" : "/");

  const topNavSection =
    location.pathname === "/leaderboard" || location.state?.from === "leaderboard"
      ? "players"
      : "standings";

  const divisions = useMemo(() => {
    const set = new Set(standings.map((r) => r.division).filter(Boolean));
    return Array.from(set).sort(
      (a, b) => DIVISION_ORDER.indexOf(a) - DIVISION_ORDER.indexOf(b)
    );
  }, [standings]);

  const playoffOddsByTeam = useMemo(() => {
    const map = {};
    playoffOdds.forEach((t) => {
      map[t.team_abbrev] = t.playoff_pct;
    });
    return map;
  }, [playoffOdds]);

  const isSearching = search.trim().length > 0;

  const visibleRows = useMemo(() => {
    let rows = standings;
    if (isSearching) {
      const q = search.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          r.team_name.toLowerCase().includes(q) ||
          r.team_abbrev.toLowerCase().includes(q)
      );
    } else if (activeDivision) {
      rows = rows.filter((r) => r.division === activeDivision);
    }
    return rows;
  }, [standings, activeDivision, search, isSearching]);

  const selectedRow = useMemo(
    () => standings.find((r) => r.team_abbrev === selectedTeam),
    [standings, selectedTeam]
  );

  return (
    <div className="dashboard">
      <style>{`
        .dashboard {
          --accent: #3b82f6;
          --bg: #0a0b0f;
          --card: #12141a;
          --border: #1f2430;
          --text: #e5e7eb;
          --text-dim: #8b93a3;
          background: var(--bg);
          color: var(--text);
          font-family: 'Inter', system-ui, sans-serif;
          min-height: 100%;
          padding: 0 0 32px 0;
        }
        .topnav {
          display: flex;
          align-items: center;
          gap: 24px;
          padding: 16px 24px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 20px;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .brand-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--accent);
        }
        .brand-name {
          font-weight: 700;
          font-size: 15px;
          color: var(--text);
        }
        .nav-tabs {
          display: flex;
          gap: 4px;
          flex: 1;
        }
        .nav-tab {
          background: none;
          border: none;
          color: var(--text-dim);
          font-size: 14px;
          font-weight: 500;
          padding: 8px 4px;
          cursor: pointer;
          border-bottom: 2px solid transparent;
        }
        .nav-tab-active {
          color: var(--text);
          border-bottom: 2px solid var(--accent);
        }
        .nav-right {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        .search-input {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 7px 12px;
          color: var(--text);
          font-size: 13px;
          width: 200px;
        }
        .search-input::placeholder { color: var(--text-dim); }
        .live-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          font-weight: 700;
          color: #22c55e;
          background: rgba(34, 197, 94, 0.1);
          padding: 5px 10px;
          border-radius: 12px;
          letter-spacing: 0.05em;
        }
        .live-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #22c55e;
        }
        .division-tabs {
          display: flex;
          gap: 8px;
          padding: 0 24px;
          margin-bottom: 16px;
        }
        .division-tab {
          background: var(--card);
          border: 1px solid var(--border);
          color: var(--text-dim);
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          padding: 6px 14px;
          border-radius: 6px;
          cursor: pointer;
        }
        .division-tab-active {
          color: var(--accent);
          border-color: var(--accent);
          background: rgba(59, 130, 246, 0.1);
        }
        .division-tabs-disabled .division-tab {
          opacity: 0.4;
          cursor: not-allowed;
        }
        .no-results {
          text-align: center;
          color: var(--text-dim);
          padding: 24px 14px;
        }
        .table-card {
          margin: 0 24px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          overflow: hidden;
        }
        .standings-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }
        .standings-table thead th {
          text-align: right;
          font-weight: 500;
          color: var(--text-dim);
          font-size: 11px;
          letter-spacing: 0.05em;
          padding: 12px 14px;
          border-bottom: 1px solid var(--border);
        }
        .standings-table th.col-team, .standings-table td.col-team { text-align: left; }
        .standings-table td {
          text-align: right;
          padding: 10px 14px;
          border-bottom: 1px solid var(--border);
        }
        .standings-table tbody tr:last-child td { border-bottom: none; }
        .standings-table tbody tr {
          cursor: pointer;
          transition: background 0.12s ease;
        }
        .standings-table tbody tr:hover { background: #171a22; }
        .row-selected { background: #161d2e !important; }
        .row-selected .team-abbrev { color: var(--accent); }
        .col-rank { color: var(--text-dim); width: 28px; }
        .col-pts { font-weight: 700; color: var(--accent); }
        .team-abbrev {
          font-weight: 700;
          margin-right: 10px;
        }
        .team-name {
          color: var(--text-dim);
          font-size: 12px;
        }
        .diff-pos { color: #22c55e; }
        .diff-neg { color: #ef4444; }
        .streak {
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 4px;
        }
        .streak-w { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
        .streak-l { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
        .streak-ot { background: rgba(234, 179, 8, 0.15); color: #eab308; }
        .streak-none { color: var(--text-dim); }
        .detail-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 16px;
          margin: 24px 24px 0 24px;
        }
        .team-card {
          flex: 0 1 260px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 20px;
        }
        .team-card-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 14px;
        }
        .team-logo {
          width: 40px;
          height: 40px;
          object-fit: contain;
        }
        .team-card-name {
          font-weight: 700;
          font-size: 15px;
        }
        .team-card-division {
          font-size: 12px;
          color: var(--text-dim);
        }
        .playoff-badge {
          display: inline-block;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.05em;
          padding: 4px 10px;
          border-radius: 12px;
          margin-bottom: 14px;
        }
        .playoff-in { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
        .playoff-out { background: rgba(139, 147, 163, 0.15); color: var(--text-dim); }
        .team-card-record {
          display: flex;
          align-items: baseline;
          gap: 8px;
          margin-bottom: 16px;
        }
        .team-card-pts {
          font-size: 24px;
          font-weight: 700;
          color: var(--accent);
        }
        .team-card-sub {
          font-size: 12px;
          color: var(--text-dim);
        }
        .team-card-splits {
          display: flex;
          justify-content: space-between;
          border-top: 1px solid var(--border);
          padding-top: 14px;
          margin-bottom: 14px;
        }
        .split {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .split-label {
          font-size: 10px;
          letter-spacing: 0.05em;
          color: var(--text-dim);
        }
        .split-value {
          font-size: 13px;
          font-weight: 600;
        }
        .team-card-ranks {
          display: flex;
          justify-content: space-between;
          border-top: 1px solid var(--border);
          padding-top: 14px;
        }
        .rank-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .rank-value {
          font-size: 13px;
          font-weight: 600;
        }
        .rank-label {
          font-size: 10px;
          color: var(--text-dim);
        }
        .trend-panel {
          flex: 1 1 400px;
          min-width: 0;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 20px;
        }
        .trend-header {
          display: flex;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 8px;
        }
        .trend-eyebrow {
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--text-dim);
        }
        .trend-team {
          font-weight: 700;
          font-size: 18px;
          color: var(--accent);
          flex: 1;
        }
        .trend-toggle {
          display: flex;
          gap: 4px;
        }
        .toggle-btn {
          background: var(--bg);
          border: 1px solid var(--border);
          color: var(--text-dim);
          font-size: 11px;
          font-weight: 600;
          padding: 5px 10px;
          border-radius: 6px;
          cursor: pointer;
        }
        .toggle-btn-active {
          color: var(--accent);
          border-color: var(--accent);
          background: rgba(59, 130, 246, 0.1);
        }
        .years-legend {
          display: flex;
          gap: 16px;
          margin-top: 8px;
          font-size: 11px;
          color: var(--text-dim);
        }
        .legend-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 2px;
          margin-right: 6px;
        }
        .legend-dot-playoff { background: #3b82f6; }
        .legend-dot-missed { background: #4b5563; }
        .status-line {
          font-size: 13px;
          color: var(--text-dim);
          padding: 0 24px;
        }
        .status-error { color: #ef4444; }
        .roster-link {
          width: 100%;
          margin-top: 14px;
          background: none;
          border: 1px solid var(--border);
          color: var(--accent);
          font-size: 12px;
          font-weight: 600;
          padding: 8px 0;
          border-radius: 6px;
          cursor: pointer;
        }
        .back-link {
          background: none;
          border: none;
          color: var(--text-dim);
          font-size: 13px;
          padding: 0 24px;
          margin-bottom: 16px;
          cursor: pointer;
        }
        .back-link:hover { color: var(--text); }
        .roster-panel, .player-panel { padding-top: 4px; }
        .roster-header {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 0 24px;
          margin-bottom: 20px;
        }
        .team-logo-lg { width: 48px; height: 48px; object-fit: contain; }
        .roster-team-name { font-weight: 700; font-size: 20px; }
        .roster-team-sub { font-size: 12px; color: var(--text-dim); }
        .roster-section-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          color: var(--text-dim);
          padding: 0 24px;
          margin-bottom: 8px;
        }
        .roster-section { margin-bottom: 20px; }
        .player-thumb {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          object-fit: cover;
          object-position: top;
          margin-right: 10px;
          background: var(--bg);
          vertical-align: middle;
        }
        .player-name-cell { vertical-align: middle; }
        .player-header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 0 24px;
          margin-bottom: 20px;
        }
        .player-headshot {
          width: 72px;
          height: 72px;
          border-radius: 50%;
          object-fit: cover;
          object-position: top;
          background: var(--card);
          border: 1px solid var(--border);
        }
        .player-name { font-weight: 700; font-size: 22px; }
        .player-sub {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: var(--text-dim);
          margin-top: 2px;
        }
        .player-team-logo { width: 18px; height: 18px; object-fit: contain; }
        .player-bio {
          display: flex;
          flex-wrap: wrap;
          gap: 20px;
          margin: 0 24px 20px 24px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 16px 20px;
        }
        .bio-item { display: flex; flex-direction: column; gap: 3px; }
        .bio-label { font-size: 10px; letter-spacing: 0.05em; color: var(--text-dim); }
        .bio-value { font-size: 13px; font-weight: 600; }
        .stat-tiles {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin: 0 24px;
        }
        .stat-tile {
          flex: 1 1 100px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .stat-tile-value { font-size: 24px; font-weight: 700; color: var(--accent); }
        .stat-tile-label { font-size: 10px; letter-spacing: 0.05em; color: var(--text-dim); }
        .leaderboard-panel { padding-top: 0; }
        .leaderboard-controls {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 0 24px;
          margin-bottom: 16px;
        }
        .leaderboard-search { width: 220px; }
        .leaderboard-group-tabs { display: flex; gap: 8px; }
        .leaderboard-table-card { margin: 0 24px; }
        .sortable-col { cursor: pointer; user-select: none; }
        .sortable-col:hover { color: var(--text); }
        .sortable-col-active { color: var(--accent); }
        .leaderboard-team-logo {
          width: 20px;
          height: 20px;
          object-fit: contain;
          margin-right: 8px;
          vertical-align: middle;
        }
        .advanced-stats-panel { margin: 20px 24px 0 24px; }
        .advanced-stats-header { margin-bottom: 10px; }
        .advanced-stats-caveat {
          font-size: 11px;
          color: var(--text-dim);
          margin-top: 10px;
          line-height: 1.5;
        }
        .col-po { width: 48px; font-weight: 700; }
        .po-in { color: #22c55e; }
        .po-out { color: var(--text-dim); }
      `}</style>

      <TopNav
        section={topNavSection}
        onNavigate={handleNavigate}
        search={search}
        onSearchChange={setSearch}
      />

      {status === "loading" && <div className="status-line">Loading standings…</div>}
      {status === "error" && (
        <div className="status-line status-error">
          Couldn't reach the API at {API_BASE}.
        </div>
      )}

      {status === "ready" && (
        <Routes>
          <Route
            path="/"
            element={
              <StandingsPage
                divisions={divisions}
                activeDivision={activeDivision}
                onSelectDivision={setActiveDivision}
                isSearching={isSearching}
                visibleRows={visibleRows}
                selectedTeam={selectedTeam}
                onSelectTeam={setSelectedTeam}
                playoffOddsByTeam={playoffOddsByTeam}
                playoffOddsStatus={playoffOddsStatus}
                selectedRow={selectedRow}
                history={history}
                seasonHistory={seasonHistory}
                trendMode={trendMode}
                onTrendModeChange={setTrendMode}
                onViewRoster={handleViewRoster}
              />
            }
          />
          <Route
            path="/teams/:teamAbbrev"
            element={<RosterPage key={location.pathname} standings={standings} />}
          />
          <Route path="/players/:playerId" element={<PlayerPage key={location.pathname} />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </div>
  );
}