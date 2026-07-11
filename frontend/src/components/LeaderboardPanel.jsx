import { useState, useMemo } from "react";

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

export default LeaderboardPanel;
