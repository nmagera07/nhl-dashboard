import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { shortDateLabel } from "../utils/dates.js";
import LineupGrid from "./LineupGrid.jsx";
import { rosterIndex } from "../utils/rosterIndex.js";

// One team's forward lines and defense pairs from its last game (GET
// /teams/{team}/lines, worked out from NHL shift charts; each line left
// wing, center, right wing, ranked by time together). The fallback before
// NHL.com posts tonight's projected lineup, and the lines on team pages.
// `showTeam` puts the team's abbreviation in front of the game it's from.
function TeamLines({ abbrev, showTeam = true }) {
  const { data, status } = useFetchWithStatus(`${API_BASE}/teams/${abbrev}/lines`);
  // Headshots and numbers; the lines still show (names only) without it.
  const { data: roster } = useFetchWithStatus(`${API_BASE}/teams/${abbrev}/roster`);
  if (status === "error") return <p className="preview-note">Couldn&apos;t load {abbrev}&apos;s lines.</p>;
  if (!data) return <p className="preview-note">Loading…</p>;
  if (!data.game) return <p className="preview-note">No {abbrev} lines yet this season.</p>;
  const { date, opponent, home } = data.game;
  const index = rosterIndex(roster);
  const lines = (groups) => groups.map((g) => ({
    players: g.players.map((name, i) => ({ name, player: index.byId(g.player_ids?.[i]) })),
  }));
  return (
    <div className="preview-lines-team">
      <h3>
        {showTeam && <>{abbrev} </>}
        <span className="muted">{showTeam ? "· " : ""}Last game: {shortDateLabel(date)} {home ? "vs" : "@"} {opponent}</span>
      </h3>
      <LineupGrid team={abbrev} forwards={lines(data.lines)} defense={lines(data.pairs)} />
    </div>
  );
}

export default TeamLines;
