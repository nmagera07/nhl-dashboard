import DivisionTabs from "../components/DivisionTabs.jsx";
import StandingsTable from "../components/StandingsTable.jsx";
import TeamCard from "../components/TeamCard.jsx";

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
  onViewRoster,
  sortBy,
  sortDir,
  onSort,
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
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={onSort}
      />
      {playoffOddsStatus === "error" && (
        <div className="status-line status-error">
          Playoff odds unavailable — the PO% column may be incomplete.
        </div>
      )}
      {selectedRow && (
        <div className="detail-grid">
          <TeamCard team={selectedRow} onViewRoster={onViewRoster} />
        </div>
      )}
    </>
  );
}

export default StandingsPage;
