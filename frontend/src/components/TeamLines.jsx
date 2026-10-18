import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { shortDateLabel } from "../utils/dates.js";

// One group of lines, labeled L1, L2... or D1, D2..., names joined by dashes.
export function LineList({ items, prefix, label }) {
  if (!items.length) return null;
  return (
    <ol className="preview-lines-list" aria-label={label}>
      {items.map((players, i) => (
        <li key={players.join("-")}>
          <span className="preview-lines-tag">{players.length === 1 && prefix === "D" ? "7D" : `${prefix}${i + 1}`}</span>
          <span>{players.join(" – ")}</span>
        </li>
      ))}
    </ol>
  );
}

// One team's forward lines and defense pairs from its last game (GET
// /teams/{team}/lines, worked out from NHL shift charts; each line left
// wing, center, right wing, ranked by time together). The fallback before
// NHL.com posts tonight's projected lineup, and the lines on team pages.
// `showTeam` puts the team's abbreviation in front of the game it's from.
function TeamLines({ abbrev, showTeam = true }) {
  const { data, status } = useFetchWithStatus(`${API_BASE}/teams/${abbrev}/lines`);
  if (status === "error") return <p className="preview-note">Couldn&apos;t load {abbrev}&apos;s lines.</p>;
  if (!data) return <p className="preview-note">Loading…</p>;
  if (!data.game) return <p className="preview-note">No {abbrev} lines yet this season.</p>;
  const { date, opponent, home } = data.game;
  return (
    <div className="preview-lines-team">
      <h3>
        {showTeam && <>{abbrev} </>}
        <span className="muted">{showTeam ? "· " : ""}Last game: {shortDateLabel(date)} {home ? "vs" : "@"} {opponent}</span>
      </h3>
      <LineList items={data.lines.map((l) => l.players)} prefix="L" label={`${abbrev} forward lines`} />
      <LineList items={data.pairs.map((l) => l.players)} prefix="D" label={`${abbrev} defense pairs`} />
    </div>
  );
}

export default TeamLines;
