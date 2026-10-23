import { useEffect } from "react";
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
  const team = playerDetail?.team_abbrev;
  const backLabel = cameFromLeaderboard ? "Back to Players" : team ? `Back to ${team} roster` : "Back to Players";
  const handleBack = () => {
    if (cameFromLeaderboard) navigate("/players");
    else navigate(team ? `/teams/${team}` : "/players");
  };

  // The tab names the player once loaded ("Connor McDavid (EDM) | PuckPulse"), like game pages.
  const name = playerDetail ? `${playerDetail.first_name} ${playerDetail.last_name}` : null;
  useEffect(() => {
    if (name) document.title = `${name}${team ? ` (${team})` : ""} | PuckPulse`;
  }, [name, team]);

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
