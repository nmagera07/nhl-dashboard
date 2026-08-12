import { useState, useEffect, useMemo } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import "./App.css";
import { API_BASE, DIVISION_ORDER } from "./config.js";
import IntelligencePanel from "./components/IntelligencePanel.jsx";
import { useFetchWithStatus } from "./hooks/useFetchWithStatus.js";
import TopNav from "./components/TopNav.jsx";
import StandingsPage from "./pages/StandingsPage.jsx";
import RosterPage from "./pages/RosterPage.jsx";
import PlayerPage from "./pages/PlayerPage.jsx";
import LeaderboardPage from "./pages/LeaderboardPage.jsx";
import GamePage from "./pages/GamePage.jsx";
import Scoreboard from "./components/Scoreboard.jsx";

export default function NHLDashboard() {
  const [history, setHistory] = useState([]);
  const [seasonHistory, setSeasonHistory] = useState([]);
  const [trendMode, setTrendMode] = useState("season"); // season | years
  const [selectedTeam, setSelectedTeam] = useState("PIT");
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

  const intelligenceContext = useMemo(() => {
    const player = location.pathname.match(/^\/players\/(\d+)/);
    if (player) return { page: "player", player_id: Number(player[1]) };

    const team = location.pathname.match(/^\/teams\/([A-Za-z]{2,3})/);
    if (team) return { page: "team", team_abbrev: team[1].toUpperCase() };

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

  const selectedRow = useMemo(
    () => standings.find((r) => r.team_abbrev === selectedTeam),
    [standings, selectedTeam]
  );

  return (
    <div className="dashboard">
      <TopNav
        section={topNavSection}
        onNavigate={handleNavigate}
        search={search}
        onSearchChange={setSearch}
      />
      <Scoreboard />
      <IntelligencePanel context={intelligenceContext} />

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
                sortBy={standingsSortBy}
                sortDir={standingsSortDir}
                onSort={handleStandingsSort}
              />
            }
          />
          <Route
            path="/teams/:teamAbbrev"
            element={<RosterPage key={location.pathname} standings={standings} />}
          />
          <Route path="/players/:playerId" element={<PlayerPage key={location.pathname} />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/games/:gameId" element={<GamePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </div>
  );
}
