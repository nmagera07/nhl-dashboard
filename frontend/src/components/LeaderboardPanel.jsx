import { teamLogo } from "../utils/teamLogo.js";
import { useState, useMemo } from "react";
import StatAbbr from "./StatAbbr.jsx";
import StatGlossary from "./StatGlossary.jsx";
import AllPlayerSearch from "./AllPlayerSearch.jsx";
import { formatSigned, formatToi } from "../utils/format.js";

// The Players page fetches /players/leaders?view=table, which returns only
// the fields in backend PlayerLeaderTableRow (response_models/players.py).
// A new column here needs its field added to PlayerLeaderTableRow too, or
// it will render blank.
const SKATER_COLUMNS = [
  { key: "points", label: "PTS" },
  { key: "goals", label: "G" },
  { key: "assists", label: "A" },
  { key: "plus_minus", label: "+/-" },
  { key: "pim", label: "PIM" },
  { key: "shots", label: "SHOTS" },
  { key: "avg_toi_seconds", label: "TOI" },
  { key: "war", label: "WAR" },
  { key: "games_played", label: "GP" },
];

const GOALIE_COLUMNS = [
  { key: "wins", label: "W" },
  { key: "losses", label: "L" },
  { key: "ot_losses", label: "OTL" },
  { key: "goals_against_avg", label: "GAA" },
  { key: "save_pctg", label: "SV%" },
  { key: "shutouts", label: "SO" },
  { key: "war", label: "WAR" },
  { key: "games_played", label: "GP" },
];

const LOWER_IS_BETTER = new Set(["goals_against_avg", "losses", "ot_losses", "pim"]);
const LEADERBOARD_PAGE_SIZE = 50;

function formatStatValue(key, value) {
  if (value == null) return "—";
  if (key === "goals_against_avg") return Number(value).toFixed(2);
  if (key === "save_pctg") return Number(value).toFixed(3);
  if (key === "avg_toi_seconds") return formatToi(value);
  if (key === "war") return formatSigned(value, 2);
  return value;
}

function getVisiblePages(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  if (current > 3) pages.push("…");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p);
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

function LeaderboardPanel({ players, onSelectPlayer }) {
  const [group, setGroup] = useState("skaters"); // skaters | goalies
  const [sortKey, setSortKey] = useState("points");
  const [sortDir, setSortDir] = useState("desc");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const columns = group === "goalies" ? GOALIE_COLUMNS : SKATER_COLUMNS;

  const handleGroupChange = (nextGroup) => {
    setGroup(nextGroup);
    setSortKey(nextGroup === "goalies" ? "wins" : "points");
    setSortDir("desc");
    setPage(1);
  };

  const handleSort = (key) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(LOWER_IS_BETTER.has(key) ? "asc" : "desc");
    }
    setPage(1);
  };

  const handleSearchChange = (value) => {
    setSearch(value);
    setPage(1);
  };

  const isSearching = search.trim().length > 0;
  const rosterIds = useMemo(() => new Set(players.map((p) => p.player_id)), [players]);

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

  const totalPages = Math.max(1, Math.ceil(sorted.length / LEADERBOARD_PAGE_SIZE));
  const effectivePage = Math.min(page, totalPages);
  const startIdx = (effectivePage - 1) * LEADERBOARD_PAGE_SIZE;
  const paged = sorted.slice(startIdx, startIdx + LEADERBOARD_PAGE_SIZE);

  const rangeStart = sorted.length === 0 ? 0 : startIdx + 1;
  const rangeEnd = Math.min(startIdx + LEADERBOARD_PAGE_SIZE, sorted.length);

  // Phone rows: the headline stat big on the right, WAR beside it, and a
  // few supporting stats on the line under the name.
  const headlineKey = group === "goalies" ? "wins" : "points";
  const lineKeys = group === "goalies" ? ["save_pctg", "goals_against_avg", "shutouts"] : ["goals", "assists", "avg_toi_seconds"];
  const lineColumns = lineKeys.map((key) => columns.find((col) => col.key === key));

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
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </div>

      <div className="status-line">
        {isSearching
          ? `${sorted.length} result${sorted.length === 1 ? "" : "s"} for "${search.trim()}"${totalPages > 1 ? ` — page ${effectivePage} of ${totalPages}` : ""}`
          : totalPages > 1
            ? `Showing ${rangeStart}–${rangeEnd} of ${sorted.length} — page ${effectivePage} of ${totalPages}`
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
                  <StatAbbr term={col.label} />{col.key === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 && (
              <tr>
                <td colSpan={2 + columns.length} className="no-results">No players match your search.</td>
              </tr>
            )}
            {paged.map((p, i) => (
              <tr key={p.player_id} onClick={() => onSelectPlayer(p.player_id)}>
                <td className="col-rank">{startIdx + i + 1}</td>
                <td className="col-team">
                  {p.team_logo_url && <img className="leaderboard-team-logo" src={teamLogo(p.team_logo_url)} alt="" />}
                  <span className="team-abbrev">{p.team_abbrev}</span>
                  <span className="team-name" title={`${p.first_name} ${p.last_name}`}>{p.first_name} {p.last_name}</span>
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

      <div className="leaderboard-mobile-list" aria-label={`${group} player cards`}>
        {paged.length === 0 && <div className="leaderboard-mobile-empty">No players match your search.</div>}
        {paged.map((p, i) => (
          <button
            className="leaderboard-row"
            key={p.player_id}
            type="button"
            aria-label={`Open ${p.first_name} ${p.last_name} profile`}
            onClick={() => onSelectPlayer(p.player_id)}
          >
            <span className="leaderboard-row-rank">{startIdx + i + 1}</span>
            {p.team_logo_url ? <img className="leaderboard-team-logo" src={teamLogo(p.team_logo_url)} alt="" /> : <span className="leaderboard-team-logo" />}
            <span className="leaderboard-row-player">
              <strong>{p.first_name} {p.last_name}</strong>
              <small>
                <span>{p.team_abbrev} · {p.position_code}</span>
                {lineColumns.map((col) => (
                  <span key={col.key}><b>{formatStatValue(col.key, p[col.key])}</b> {col.label}</span>
                ))}
              </small>
            </span>
            <span className="leaderboard-row-war"><strong>{formatStatValue("war", p.war)}</strong><small>WAR</small></span>
            <span className="leaderboard-row-headline">
              <strong>{formatStatValue(headlineKey, p[headlineKey])}</strong>
              <small>{group === "goalies" ? "W" : "PTS"}</small>
            </span>
          </button>
        ))}
      </div>

      {totalPages > 1 && (
        <nav className="pagination" aria-label="Leaderboard pagination">
          <button
            className="pagination-btn"
            disabled={effectivePage === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            aria-label="Previous page"
          >
            ‹ Prev
          </button>
          <div className="pagination-pages">
            {getVisiblePages(effectivePage, totalPages).map((p, idx) =>
              p === "…" ? (
                <span key={`ellipsis-${idx}`} className="pagination-ellipsis">…</span>
              ) : (
                <button
                  key={p}
                  className={p === effectivePage ? "pagination-btn pagination-btn-active" : "pagination-btn"}
                  onClick={() => setPage(p)}
                  aria-label={`Page ${p}`}
                  aria-current={p === effectivePage ? "page" : undefined}
                >
                  {p}
                </button>
              )
            )}
          </div>
          <button
            className="pagination-btn"
            disabled={effectivePage === totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            aria-label="Next page"
          >
            Next ›
          </button>
        </nav>
      )}
      {isSearching && (
        <AllPlayerSearch query={search} exclude={rosterIds} onSelectPlayer={onSelectPlayer} />
      )}
      <StatGlossary terms={columns.map((col) => col.label)} />
    </div>
  );
}

export default LeaderboardPanel;
