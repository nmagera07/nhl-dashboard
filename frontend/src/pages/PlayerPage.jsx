import { useNavigate, useLocation, useParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import PlayerPanel from "../components/PlayerPanel.jsx";

function PlayerPage() {
  const { playerId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const { data: playerDetail, status: playerStatus } = useFetchWithStatus(
    `${API_BASE}/players/${playerId}`
  );

  // Prefer the explicit "where did you come from" state passed at navigation
  // time; a direct deep link (no state) falls back to the player's own team
  // roster, which is always a sensible destination and doesn't depend on
  // browser history existing at all.
  const cameFromLeaderboard = location.state?.from === "leaderboard";
  const backLabel = cameFromLeaderboard ? "Back to Leaderboard" : "Back to Roster";
  const handleBack = () => {
    if (cameFromLeaderboard) navigate("/leaderboard");
    else navigate(playerDetail?.team_abbrev ? `/teams/${playerDetail.team_abbrev}` : "/");
  };

  return (
    <>
      {playerStatus === "loading" && <div className="status-line">Loading player…</div>}
      {playerStatus === "error" && (
        <div className="status-line status-error">Couldn't load player details.</div>
      )}
      {playerStatus === "ready" && (
        <PlayerPanel player={playerDetail} onBack={handleBack} backLabel={backLabel} />
      )}
    </>
  );
}

export default PlayerPage;
