import { Link } from "react-router-dom";
import DivisionTabs from "../components/DivisionTabs.jsx";
import StandingsTable from "../components/StandingsTable.jsx";

const VIEWS = [
  { key: "standard", label: "Standard" },
  { key: "advanced", label: "Advanced" },
];

function StandingsPage({
  divisions,
  activeDivision,
  onSelectDivision,
  isSearching,
  visibleRows,
  onSelectTeam,
  playoffOddsByTeam,
  playoffOddsStatus,
  view,
  onViewChange,
  sortBy,
  sortDir,
  onSort,
}) {
  return (
    <main>
      <div className="page-header page">
        <h1>Standings</h1>
      </div>
      <div className="standings-controls">
        <DivisionTabs
          divisions={divisions}
          active={activeDivision}
          onSelect={onSelectDivision}
          disabled={isSearching}
        />
        {/* Desktop only: phones show the standard stats as cards. */}
        <div className="view-toggle" role="group" aria-label="Stats view">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              className={v.key === view ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"}
              aria-pressed={v.key === view}
              onClick={() => onViewChange(v.key)}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <StandingsTable
        rows={visibleRows}
        onSelectTeam={onSelectTeam}
        playoffOddsByTeam={playoffOddsByTeam}
        view={view}
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={onSort}
      />
      <p className="data-credit">
        {view === "advanced"
          ? "5-on-5 advanced stats (xG%, xGF, xGA, shots, PDO) courtesy of "
          : "Playoff odds (PO%) blend goals with expected goals (xG) courtesy of "}
        <a href="https://moneypuck.com" target="_blank" rel="noreferrer">MoneyPuck.com</a>.
        {view === "standard" && <> <Link to="/playoffs">See the playoff race →</Link></>}
      </p>
      {playoffOddsStatus === "error" && (
        <div className="status-line status-error">
          Playoff odds unavailable — the PO% column may be incomplete.
        </div>
      )}
    </main>
  );
}

export default StandingsPage;
