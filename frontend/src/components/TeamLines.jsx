import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { shortDateLabel } from "../utils/dates.js";

// One team's forward lines and defense pairs from its last game (GET
// /teams/{team}/lines, worked out from NHL shift charts). Used in game
// previews and, collapsed, on team pages. `showTeam` puts the team's
// abbreviation in front of the game it's from.
function TeamLines({ abbrev, showTeam = true }) {
  const { data, status } = useFetchWithStatus(`${API_BASE}/teams/${abbrev}/lines`);
  if (status === "error") return <p className="preview-note">Couldn&apos;t load {abbrev}&apos;s lines.</p>;
  if (!data) return <p className="preview-note">Loading…</p>;
  const group = (items, label) =>
    items.length > 0 && (
      <ol className="preview-lines-list" aria-label={`${abbrev} ${label}`}>
        {items.map((l) => (
          <li key={l.player_ids.join("-")}>
            <span>{l.players.join(" – ")}</span>
            <span className="muted">{l.minutes} min</span>
          </li>
        ))}
      </ol>
    );
  if (!data.game) return <p className="preview-note">No {abbrev} lines yet this season.</p>;
  const { date, opponent, home } = data.game;
  return (
    <div className="preview-lines-team">
      <h3>
        {showTeam && <>{abbrev} </>}
        <span className="muted">{showTeam ? "· " : "Last game: "}{shortDateLabel(date)} {home ? "vs" : "@"} {opponent}</span>
      </h3>
      {group(data.lines, "forward lines")}
      {group(data.pairs, "defense pairs")}
    </div>
  );
}

export default TeamLines;
