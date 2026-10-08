import { useState, useMemo } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import "./App.css";
import { API_BASE, DIVISION_ORDER } from "./config.js";
import IntelligencePanel from "./components/IntelligencePanel.jsx";
import { useFetchWithStatus } from "./hooks/useFetchWithStatus.js";
import TopNav from "./components/TopNav.jsx";
import TabBar from "./components/TabBar.jsx";
import ScoresPage from "./pages/ScoresPage.jsx";
import StandingsPage from "./pages/StandingsPage.jsx";
import RosterPage from "./pages/RosterPage.jsx";
import PlayerPage from "./pages/PlayerPage.jsx";
import LeaderboardPage from "./pages/LeaderboardPage.jsx";
import GamePage from "./pages/GamePage.jsx";

export default function NHLDashboard() {
  const [standingsView, setStandingsView] = useState("standard"); // standard | advanced
  const [activeDivision, setActiveDivision] = useState(null);
  const [search, setSearch] = useState("");
  const [standingsSortBy, setStandingsSortBy] = useState(null);
  const [standingsSortDir, setStandingsSortDir] = useState("desc");

  const navigate = useNavigate();
  const location = useLocation();

  const standingsUrl = standingsSortBy
    ? `${API_BASE}/standings/latest?sort_by=${standingsSortBy}&sort_dir=${standingsSortDir}`
    : `${API_BASE}/standings/latest`;

  const { data: standings, status } = useFetchWithStatus(standingsUrl, {
    initialData: [],
    onSuccess: (data) => {
      // Only seed the default division tab on first load -- re-fetches
      // triggered by clicking a sortable column reorder the same teams,
      // they don't mean "switch the user's selected division tab."
      if (activeDivision != null) return;
      const firstDivision = data.find((d) => d.division)?.division;
      if (firstDivision) setActiveDivision(firstDivision);
    },
  });

  const handleStandingsSort = (key) => {
    if (key === standingsSortBy) {
      setStandingsSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setStandingsSortBy(key);
      setStandingsSortDir("desc");
    }
  };

  const { data: playoffOdds, status: playoffOddsStatus } = useFetchWithStatus(
    `${API_BASE}/playoff-odds`,
    { initialData: [], transform: (data) => (Array.isArray(data) ? data : []) }
  );

  const handleSelectTeam = (teamAbbrev) => navigate(`/teams/${teamAbbrev}`);

  // Sorting is only offered on advanced columns, so leaving that view drops
  // the sort -- otherwise teams would stay ordered by a hidden column.
  const handleStandingsViewChange = (view) => {
    setStandingsView(view);
    if (view === "standard") setStandingsSortBy(null);
  };

  const intelligenceContext = useMemo(() => {
    const player = location.pathname.match(/^\/players\/(\d+)/);
    if (player) return { page: "player", player_id: Number(player[1]) };

    const team = location.pathname.match(/^\/teams\/([A-Za-z]{2,3})/);
    if (team) return { page: "team", team_abbrev: team[1].toUpperCase() };

    const game = location.pathname.match(/^\/games\/(\d+)/);
    if (game) return { page: "game", game_id: Number(game[1]) };

    // nhl-intelligence only accepts player | team | standings, so other
    // pages (scores) use the general league context.
    return { page: "standings" };
  }, [location.pathname]);

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

  // Standings data is fetched once here and shared (the standings page and
  // team pages both use it), but only the standings page waits on it.
  const standingsGate =
    status === "loading" ? <div className="status-line">Loading standings…</div>
    : status === "error" ? <div className="status-line status-error">Couldn't reach the API at {API_BASE}.</div>
    : null;

  return (
    <div className="dashboard">
      <TopNav search={search} onSearchChange={setSearch} />
      <IntelligencePanel context={intelligenceContext} />

      <div className="app-content">
        <Routes>
          <Route path="/" element={<ScoresPage />} />
          <Route
            path="/standings"
            element={standingsGate || (
              <StandingsPage
                divisions={divisions}
                activeDivision={activeDivision}
                onSelectDivision={setActiveDivision}
                isSearching={isSearching}
                visibleRows={visibleRows}
                onSelectTeam={handleSelectTeam}
                playoffOddsByTeam={playoffOddsByTeam}
                playoffOddsStatus={playoffOddsStatus}
                view={standingsView}
                onViewChange={handleStandingsViewChange}
                sortBy={standingsSortBy}
                sortDir={standingsSortDir}
                onSort={handleStandingsSort}
              />
            )}
          />
          <Route
            path="/teams/:teamAbbrev"
            element={<RosterPage key={location.pathname} standings={standings} />}
          />
          <Route path="/players" element={<LeaderboardPage />} />
          <Route path="/players/:playerId" element={<PlayerPage key={location.pathname} />} />
          <Route path="/games/:gameId" element={<GamePage />} />
          {/* Old URL, kept so existing bookmarks and installs still work. */}
          <Route path="/leaderboard" element={<Navigate to="/players" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>

      <TabBar />
    </div>
  );
}
