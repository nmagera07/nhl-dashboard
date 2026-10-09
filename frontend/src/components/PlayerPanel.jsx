import { useState } from "react";
import { Link } from "react-router-dom";
import { formatSeasonLabel } from "../utils/formatSeasonLabel.js";
import { darkLogo } from "../utils/darkLogo.js";
import StatAbbr from "./StatAbbr.jsx";
import StatGlossary from "./StatGlossary.jsx";

const POSITION_LABELS = { C: "Center", L: "Left Wing", R: "Right Wing", D: "Defense", G: "Goalie" };

// One column set per player type, shared by the season strip, career
// totals, and season-by-season tables so the numbers always line up.
const SKATER_COLUMNS = [
  { key: "games_played", label: "GP" },
  { key: "goals", label: "G" },
  { key: "assists", label: "A" },
  { key: "points", label: "PTS", highlight: true },
  { key: "plus_minus", label: "+/-" },
  { key: "shots", label: "SOG", optional: true },
  { key: "pim", label: "PIM", optional: true },
];

const GOALIE_COLUMNS = [
  { key: "games_played", label: "GP" },
  { key: "wins", label: "W" },
  { key: "losses", label: "L" },
  { key: "ot_losses", label: "OTL", optional: true },
  { key: "goals_against_avg", label: "GAA" },
  { key: "save_pctg", label: "SV%", highlight: true },
  { key: "shutouts", label: "SO", optional: true },
];

// Table cells for a column: optional columns hide on phones (the season
// strip at the top still shows every stat).
function columnClass(col) {
  return [col.highlight && "col-pts", col.optional && "col-optional"].filter(Boolean).join(" ") || undefined;
}

function formatStat(key, value) {
  if (value == null) return "—";
  if (key === "goals_against_avg") return Number(value).toFixed(2);
  if (key === "save_pctg") return Number(value).toFixed(3).replace(/^0/, "");
  if (key === "plus_minus") return value > 0 ? `+${value}` : String(value);
  return value;
}

function formatPct(value) {
  return value != null ? `${(Number(value) * 100).toFixed(1)}%` : "—";
}

function formatDecimal(value, digits = 2) {
  return value != null ? Number(value).toFixed(digits) : "—";
}

function ageOn(birthDate, today = new Date()) {
  if (!birthDate) return null;
  const born = new Date(`${birthDate}T00:00:00`);
  const age = today.getFullYear() - born.getFullYear();
  const hadBirthday =
    today.getMonth() > born.getMonth() || (today.getMonth() === born.getMonth() && today.getDate() >= born.getDate());
  return hadBirthday ? age : age - 1;
}

function heightLabel(inches) {
  return inches ? `${Math.floor(inches / 12)}'${inches % 12}"` : null;
}

function StatStrip({ stats, columns, label }) {
  return (
    <dl className="stat-strip" aria-label={label}>
      {columns.map((col) => (
        <div key={col.key} className="stat-strip-item">
          <dt>{col.label}</dt>
          <dd className={col.highlight ? "is-highlight" : undefined}>{formatStat(col.key, stats[col.key])}</dd>
        </div>
      ))}
    </dl>
  );
}

function Section({ title, aside, children }) {
  return (
    <section className="player-section">
      <div className="player-section-header">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function StatsTable({ rows, columns, firstColumn, label }) {
  return (
    <div className="table-card player-table-card">
      <table className="standings-table player-stats-table" aria-label={label}>
        <thead>
          <tr>
            <th className="col-team">{firstColumn}</th>
            {columns.map((col) => (
              <th key={col.key} className={columnClass(col)}><StatAbbr term={col.label} /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td className="col-team">{row.label}</td>
              {columns.map((col) => (
                <td key={col.key} className={columnClass(col)}>{formatStat(col.key, row.stats[col.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlayerPanel({ player, onBack, backLabel }) {
  const [showAllSeasons, setShowAllSeasons] = useState(false);
  const [seasonHistoryTab, setSeasonHistoryTab] = useState("regular_season");

  if (!player) return null;

  const isGoalie = player.position_code === "G";
  const columns = isGoalie ? GOALIE_COLUMNS : SKATER_COLUMNS;
  const seasonStats = player.season_stats?.[0];
  const advancedStats = player.advanced_stats;

  const careerRows = [
    player.career_totals?.regular_season && { key: "rs", label: "Regular season", stats: player.career_totals.regular_season },
    player.career_totals?.playoffs && { key: "po", label: "Playoffs", stats: player.career_totals.playoffs },
  ].filter(Boolean);

  const seasonHistory = player.season_history ?? [];
  const regularSeasonHistory = seasonHistory.filter((e) => e.season_type === "regular_season");
  const playoffsHistory = seasonHistory.filter((e) => e.season_type === "playoffs");
  const hasPlayoffHistory = playoffsHistory.length > 0;
  const activeSeasonHistory =
    seasonHistoryTab === "playoffs" && hasPlayoffHistory ? playoffsHistory : regularSeasonHistory;
  const visibleSeasonHistory = showAllSeasons ? activeSeasonHistory : activeSeasonHistory.slice(0, 5);

  const age = ageOn(player.birth_date);
  const bio = [
    player.shoots_catches && `${isGoalie ? "Catches" : "Shoots"} ${player.shoots_catches}`,
    heightLabel(player.height_in_inches),
    player.weight_in_pounds && `${player.weight_in_pounds} lbs`,
    age != null && `Age ${age}`,
    player.birth_city && `${player.birth_city}, ${player.birth_country}`,
  ].filter(Boolean);

  const switchSeasonTab = (tab) => {
    setSeasonHistoryTab(tab);
    setShowAllSeasons(false);
  };

  return (
    <main className="player-panel">
      <button className="back-link" onClick={onBack}>&larr; {backLabel}</button>

      <section className="player-hero" aria-label={`${player.first_name} ${player.last_name}`}>
        <div className="player-hero-identity">
          {player.headshot_url && <img className="player-headshot" src={player.headshot_url} alt="" />}
          <div className="player-hero-title">
            <h1>{player.first_name} {player.last_name}</h1>
            <p className="player-hero-sub">
              {player.team_abbrev && (
                <Link className="player-team-link" to={`/teams/${player.team_abbrev}`}>
                  {player.team_logo_url && <img className="player-team-logo" src={darkLogo(player.team_logo_url)} alt="" />}
                  {player.team_abbrev}
                </Link>
              )}
              <span>#{player.sweater_number ?? "—"}</span>
              <span>{POSITION_LABELS[player.position_code] ?? player.position_code}</span>
            </p>
            {bio.length > 0 && <p className="player-hero-bio">{bio.join(" · ")}</p>}
          </div>
        </div>

        <div className="player-hero-season">
          <div className="player-hero-season-label">
            {seasonStats ? `${formatSeasonLabel(seasonStats.season_id)} season` : "This season"}
          </div>
          {seasonStats ? (
            <StatStrip stats={seasonStats} columns={columns} label="This season" />
          ) : (
            <p className="muted">No current-season stats are available yet.</p>
          )}
        </div>
      </section>

      {!isGoalie && advancedStats && (
        <Section title="Advanced (5-on-5)">
          <div className="player-card">
            <dl className="stat-strip">
              {[
                ["Corsi %", formatPct(advancedStats.corsi_for_pct), "CORSI%"],
                ["Fenwick %", formatPct(advancedStats.fenwick_for_pct), "FENWICK%"],
                ["xG %", formatPct(advancedStats.xgoals_for_pct), "xG%"],
                ["xGF–xGA", `${formatDecimal(advancedStats.xgoals_for, 1)}–${formatDecimal(advancedStats.xgoals_against, 1)}`, "ONICE_XG"],
                ["Ind. xG", formatDecimal(advancedStats.individual_xgoals), "IND_XG"],
                ["PDO", formatDecimal(advancedStats.pdo, 1), "PDO"],
              ].map(([label, value, term]) => (
                <div key={label} className="stat-strip-item">
                  <dt><StatAbbr term={term}>{label}</StatAbbr></dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="player-card-note">
              MoneyPuck.com, {formatSeasonLabel(advancedStats.season_id)} season
              {advancedStats.games_played != null ? ` (${advancedStats.games_played} GP)` : ""}.
            </p>
          </div>
        </Section>
      )}

      {careerRows.length > 0 && (
        <Section title="Career">
          <StatsTable rows={careerRows} columns={columns} firstColumn="" label="Career totals" />
        </Section>
      )}

      {seasonHistory.length > 0 && (
        <Section
          title="Season by season"
          aside={hasPlayoffHistory && (
            <div className="view-toggle" role="group" aria-label="Season type">
              {[["regular_season", "Regular season"], ["playoffs", "Playoffs"]].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={seasonHistoryTab === key ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"}
                  aria-pressed={seasonHistoryTab === key}
                  onClick={() => switchSeasonTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        >
          <StatsTable
            rows={visibleSeasonHistory.map((entry) => ({
              key: `${entry.season_id}-${entry.season_type}`,
              label: formatSeasonLabel(entry.season_id),
              stats: entry,
            }))}
            columns={columns}
            firstColumn="SEASON"
            label="Season by season"
          />
          {activeSeasonHistory.length > 5 && (
            <button type="button" className="show-more-btn" onClick={() => setShowAllSeasons((prev) => !prev)}>
              {showAllSeasons ? "Show less" : `Show all ${activeSeasonHistory.length} seasons`}
            </button>
          )}
        </Section>
      )}
      <StatGlossary
        terms={isGoalie ? ["GP", "W", "L", "OTL", "GAA", "SV%", "SO"] : ["GP", "G", "A", "PTS", "+/-", "SOG", "PIM", "CORSI%", "FENWICK%", "xG%", "ONICE_XG", "IND_XG", "PDO"]}
        labels={{ "CORSI%": "Corsi %", "FENWICK%": "Fenwick %", "xG%": "xG %", ONICE_XG: "xGF–xGA", IND_XG: "Ind. xG" }}
      />
    </main>
  );
}

export default PlayerPanel;
