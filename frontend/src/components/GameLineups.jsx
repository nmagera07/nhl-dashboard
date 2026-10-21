import { useState } from "react";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import TeamLines from "./TeamLines.jsx";
import LineupGrid from "./LineupGrid.jsx";
import { lastName, rosterIndex } from "../utils/rosterIndex.js";

const postedTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// NHL.com's projected lineup gives names only; the roster adds headshots,
// numbers, and player links.
function ProjectedTeam({ team }) {
  const { data: roster } = useFetchWithStatus(`${API_BASE}/teams/${team.abbrev}/roster`);
  const index = rosterIndex(roster);
  const chip = (name) => ({ name: lastName(name), player: index.byName(name) });
  const lines = (groups) => groups.map((g) => ({ players: g.map(chip) }));
  return (
    <div className="preview-lines-team">
      <LineupGrid
        team={team.abbrev}
        forwards={lines(team.forwards)}
        defense={lines(team.defense)}
        goalies={team.goalies.map((name) => ({ ...chip(name), badge: "Likely starter" }))}
      />
      {team.scratched.length > 0 && (
        <p className="lineup-extra"><span className="lineup-extra-label">Scratched</span>
          {team.scratched.map((name) => <span key={name} className="lineup-tag">{name}</span>)}
        </p>
      )}
      {team.injured.length > 0 && (
        <p className="lineup-extra"><span className="lineup-extra-label">Injured</span>
          {team.injured.map((p) => <span key={p.name} className="lineup-tag lineup-tag-hurt">{p.detail ? `${p.name} (${p.detail})` : p.name}</span>)}
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
