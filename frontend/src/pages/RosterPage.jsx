import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import RosterPanel from "../components/RosterPanel.jsx";

function RosterPage({ standings }) {
  const { teamAbbrev } = useParams();
  const navigate = useNavigate();
  const abbrev = teamAbbrev?.toUpperCase();

  const { data: roster, status: rosterStatus } = useFetchWithStatus(
    `${API_BASE}/teams/${abbrev}/roster`,
    { initialData: [], transform: (data) => (Array.isArray(data) ? data : []) }
  );

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

export default RosterPage;
