import { useNavigate } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import LeaderboardPanel from "../components/LeaderboardPanel.jsx";

function LeaderboardPage() {
  const navigate = useNavigate();

  const { data: leaders, status: leadersStatus } = useFetchWithStatus(
    // Slim view: only the fields LeaderboardPanel renders (~0.5 MB vs 1.18 MB).
    `${API_BASE}/players/leaders?view=table`,
    { initialData: [], transform: (data) => (Array.isArray(data) ? data : []) }
  );

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

export default LeaderboardPage;
