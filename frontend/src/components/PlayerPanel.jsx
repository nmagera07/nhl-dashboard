import { formatSigned, formatToi } from "../utils/format.js";
import { ordinal } from "../utils/ordinal.js";
import { useState } from "react";
import { Link } from "react-router-dom";
import { formatSeasonLabel } from "../utils/formatSeasonLabel.js";
import { teamLogo } from "../utils/teamLogo.js";
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

// This season only: the career and season-by-season rows don't carry TOI.
const SEASON_TOI = { key: "avg_toi_seconds", label: "TOI", term: "ATOI" };

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
  if (key === "avg_toi_seconds") return formatToi(value);
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

// The 5-on-5 numbers as plain-language bars: what each means, his number,
// and where it ranks among his position this season ("better than 94% of
// forwards"), instead of raw totals like xGF-xGA that mean little alone.
const ADVANCED_ROWS = [
  { key: "corsi", label: "Controls play", hint: "Shot attempts for vs. against with him on the ice",
    value: (s) => formatPct(s.corsi_for_pct), term: "CORSI%", short: "Corsi %" },
  { key: "xg", label: "Wins the chance battle", hint: "Expected goals for vs. against with him on the ice",
    value: (s) => formatPct(s.xgoals_for_pct), term: "xG%", short: "xG %" },
  { key: "ixg60", label: "Creates his own chances", hint: "Expected goals from his own shots, per 60 minutes",
    value: (s, r) => (r?.ixg60_value != null ? formatDecimal(r.ixg60_value, 2) : "—"), term: "IND_XG", short: "ixG/60" },
];

function luck(pdo) {
  if (pdo == null) return null;
  const value = Number(pdo);
  if (value >= 103) return `PDO ${formatDecimal(value, 1)}: running hot (shooting and goaltending above normal), likely to cool off.`;
  if (value <= 97) return `PDO ${formatDecimal(value, 1)}: running cold, likely to pick up.`;
  return `PDO ${formatDecimal(value, 1)}: about normal luck.`;
}

function AdvancedRanks({ stats, ranks }) {
  const ranked = ranks && !ranks.too_few_minutes;
  return (
    <>
      <ul className="adv-ranks">
        {ADVANCED_ROWS.map((row) => {
          const pct = ranked ? ranks[row.key] : null;
          return (
            <li key={row.key} className="adv-rank">
              <div className="adv-rank-head">
                <span className="adv-rank-label">{row.label}</span>
                <span className="adv-rank-value"><StatAbbr term={row.term}>{row.short}</StatAbbr> {row.value(stats, ranks)}</span>
              </div>
              {pct != null && (
                <>
                  <div className="adv-rank-bar" role="img" aria-label={`Better than ${pct}% of ${ranks.group}`}>
                    <span style={{ width: `${Math.max(pct, 2)}%` }} className={pct >= 67 ? "adv-high" : pct <= 33 ? "adv-low" : undefined} />
                  </div>
                  <span className="adv-rank-hint">Better than <strong>{pct}%</strong> of {ranks.group} · {row.hint}</span>
                </>
              )}
              {pct == null && <span className="adv-rank-hint">{row.hint}</span>}
            </li>
          );
        })}
      </ul>
      {ranks?.too_few_minutes && <p className="player-card-note">Not enough 5-on-5 minutes yet to rank him against the league.</p>}
      {luck(stats.pdo) && <p className="adv-luck">{luck(stats.pdo)}</p>}
    </>
  );
}

// "WAR +0.77 · 1st of 459 forwards": this season's wins above replacement, ranked within the position.
function WarLine({ war }) {
  if (!war) return null;
  return (
    <p className="player-war">
      <StatAbbr term="WAR">WAR</StatAbbr> <strong>{formatSigned(war.war, 2)}</strong>
      <span> · {ordinal(war.rank)} of {war.of} {war.group}</span>
    </p>
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
  // Not on a current roster (retired, or between teams): built from the NHL's profile, so no team or this season.
  const former = Boolean(player.status);
  const careerRegular = player.career_totals?.regular_season;
  const columns = isGoalie ? GOALIE_COLUMNS : SKATER_COLUMNS;
  const seasonColumns = isGoalie ? GOALIE_COLUMNS : [...SKATER_COLUMNS, SEASON_TOI];
  const seasonStats = player.season_stats?.[0];
  const advancedStats = player.advanced_stats;
  const goalieAdvanced = player.goalie_advanced_stats;

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

  // A retired player's age would keep counting for players who have died (the
  // NHL's data has no death date), so their pages show the birth year instead.
  const retired = player.status === "retired";
  const age = retired ? null : ageOn(player.birth_date);
  const bio = [
    player.shoots_catches && `${isGoalie ? "Catches" : "Shoots"} ${player.shoots_catches}`,
    heightLabel(player.height_in_inches),
    player.weight_in_pounds && `${player.weight_in_pounds} lbs`,
    age != null && `Age ${age}`,
    retired && player.birth_date && `Born ${player.birth_date.slice(0, 4)}`,
    player.birth_city && `${player.birth_city}, ${player.birth_country}`,
  ].filter(Boolean);

  const switchSeasonTab = (tab) => {
    setSeasonHistoryTab(tab);
    setShowAllSeasons(false);
  };

  return (
    <main className="player-panel">
      <div className="player-topbar">
        <button className="back-link" onClick={onBack}>&larr; {backLabel}</button>
        <span className="player-topbar-links">
          {!isGoalie && <Link className="player-compare-link" to={`/time-machine?player=${player.player_id}`}>Time machine</Link>}
          <Link className="player-compare-link" to={`/compare?a=${player.player_id}`}>Compare</Link>
        </span>
      </div>

      <section className="player-hero" aria-label={`${player.first_name} ${player.last_name}`}>
        <div className="player-hero-identity">
          {player.headshot_url && <img className="player-headshot" src={player.headshot_url} alt="" />}
          <div className="player-hero-title">
            <h1>{player.first_name} {player.last_name}</h1>
            <p className="player-hero-sub">
              {player.team_abbrev && (
                <Link className="player-team-link" to={`/teams/${player.team_abbrev}`}>
                  {player.team_logo_url && <img className="player-team-logo" src={teamLogo(player.team_logo_url)} alt="" />}
                  {player.team_abbrev}
                </Link>
              )}
              <span>#{player.sweater_number ?? "—"}</span>
              <span>{POSITION_LABELS[player.position_code] ?? player.position_code}</span>
              {player.in_hall_of_fame && <span className="player-hof">Hall of Fame</span>}
            </p>
            {bio.length > 0 && <p className="player-hero-bio">{bio.join(" · ")}</p>}
          </div>
        </div>

        <div className="player-hero-season">
          <div className="player-hero-season-label">
            {seasonStats ? `${formatSeasonLabel(seasonStats.season_id)} season` : former ? "NHL career" : "This season"}
          </div>
          {!seasonStats && former && careerRegular ? (
            <>
              <StatStrip stats={careerRegular} columns={columns} label="NHL career" />
              <p className="player-former">
                {player.status === "retired" ? "Retired" : "Not on an NHL roster"} · last NHL season{" "}
                {formatSeasonLabel(player.last_season_id)}{player.last_team_name ? `, ${player.last_team_name}` : ""}
              </p>
            </>
          ) : seasonStats ? (
            <>
              <StatStrip stats={seasonStats} columns={seasonColumns} label="This season" />
              <WarLine war={player.war} />
            </>
          ) : (
            <p className="muted">No current-season stats are available yet.</p>
          )}
        </div>
      </section>

      {isGoalie && goalieAdvanced && (
        <Section title="Advanced (all situations)">
          <div className="player-card">
            <dl className="stat-strip">
              {[
                ["GSAx", formatSigned(goalieAdvanced.gsax), "GSAX"],
                ["GSAx/60", formatSigned(goalieAdvanced.gsax_per_60, 2), "GSAX60"],
                ["High-danger GSAx", formatSigned(goalieAdvanced.high_danger_gsax), "HD_GSAX"],
              ].map(([label, value, term]) => (
                <div key={label} className="stat-strip-item">
                  <dt><StatAbbr term={term}>{label}</StatAbbr></dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="player-card-note">
              {goalieAdvanced.goals_allowed != null && goalieAdvanced.xgoals_against != null
                ? `${goalieAdvanced.goals_allowed} goals allowed on shots worth ${formatDecimal(goalieAdvanced.xgoals_against, 1)} expected. `
                : ""}
              PuckPulse xG, {formatSeasonLabel(goalieAdvanced.season_id)} season
              {goalieAdvanced.games_played != null ? ` (${goalieAdvanced.games_played} GP)` : ""}.
            </p>
          </div>
        </Section>
      )}

      {!isGoalie && advancedStats && (
        <Section title="Advanced (5-on-5)">
          <div className="player-card">
            <AdvancedRanks stats={advancedStats} ranks={player.advanced_percentiles} />
            <p className="player-card-note">
              At 5-on-5. PuckPulse xG and NHL stats, {formatSeasonLabel(advancedStats.season_id)} season
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
        terms={isGoalie ? ["GP", "W", "L", "OTL", "GAA", "SV%", "SO", "GSAX", "GSAX60", "HD_GSAX", "WAR"] : ["GP", "G", "A", "PTS", "+/-", "SOG", "PIM", "ATOI", "WAR", "xG%", "CORSI%", "IND_XG", "PDO"]}
        labels={{ ATOI: "TOI", "CORSI%": "Corsi %", "xG%": "xG %", IND_XG: "ixG/60", GSAX: "GSAx", GSAX60: "GSAx/60", HD_GSAX: "High-danger GSAx" }}
      />
    </main>
  );
}

export default PlayerPanel;
