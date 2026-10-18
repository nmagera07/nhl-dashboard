import { useState } from "react";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import TeamLines, { LineList } from "./TeamLines.jsx";

// "Matthew Knies" -> "Knies", "Luca Del Bel Belluz" -> "Del Bel Belluz".
const lastName = (name) => name.split(" ").slice(1).join(" ") || name;
const postedTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

function ProjectedTeam({ team }) {
  const [starter, ...others] = team.goalies;
  return (
    <div className="preview-lines-team">
      <LineList items={team.forwards.map((l) => l.map(lastName))} prefix="L" label={`${team.abbrev} forward lines`} />
      <LineList items={team.defense.map((l) => l.map(lastName))} prefix="D" label={`${team.abbrev} defense pairs`} />
      {starter && (
        <p className="preview-lines-goalies">
          <span className="preview-lines-tag">G</span>
          <span><strong>{starter}</strong> <span className="muted">projected starter</span>{others.length > 0 && ` · ${others.join(", ")}`}</span>
        </p>
      )}
      {team.scratched.length > 0 && <p className="preview-lines-extra"><strong>Scratched:</strong> {team.scratched.join(", ")}</p>}
      {team.injured.length > 0 && (
        <p className="preview-lines-extra">
          <strong>Injured:</strong> {team.injured.map((p) => (p.detail ? `${p.name} (${p.detail})` : p.name)).join(", ")}
        </p>
      )}
    </div>
  );
}

// The game preview's lines: tonight's projected lineup from NHL.com once
// it's posted (a few hours before puck drop), else each team's lines from
// its last game. One team at a time. Collapsed until tapped, and the
// last-game lines are only fetched then; the lineup check runs up front so
// the summary can say which it is.
export default function GameLineups({ gameId, away, home }) {
  const { data } = useFetchWithStatus(`${API_BASE}/games/${gameId}/lineup`);
  const [team, setTeam] = useState("away");
  const [open, setOpen] = useState(false);
  const projected = data?.available ? data : null;
  const abbrev = team === "away" ? away.abbrev : home.abbrev;
  return (
    <section className="boxscore-card">
      <details className="preview-lines" onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <h2>Lines</h2>
          <span className="muted">{projected ? "Tonight's projected lineup · NHL.com" : "From each team's last game"}</span>
        </summary>
        {open && (
        <>
        <div className="preview-lines-toggle" role="group" aria-label="Team">
          {[["away", away.abbrev], ["home", home.abbrev]].map(([side, label]) => (
            <button key={side} type="button" aria-pressed={team === side} onClick={() => setTeam(side)}>{label}</button>
          ))}
        </div>
        {projected ? (
          <>
            <ProjectedTeam team={projected[team]} />
            <p className="preview-note">
              Projected by NHL.com{projected.published && `, posted ${postedTime(projected.published)}`}. Teams confirm at
              puck drop.{" "}
              <a className="accent-link" href={projected.url} target="_blank" rel="noreferrer">Status report on NHL.com ↗</a>
            </p>
          </>
        ) : (
          <>
            <TeamLines abbrev={abbrev} showTeam={false} />
            <p className="preview-note">
              Who played together most at even strength in {abbrev}&apos;s last game, from the NHL&apos;s shift charts.
              NHL.com&apos;s projected lineup for tonight shows up here a few hours before puck drop.
            </p>
          </>
        )}
        </>
        )}
      </details>
    </section>
  );
}
