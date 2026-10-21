import { Link } from "react-router-dom";

// One player: headshot, number, last name, linking to his page when we
// know who he is (a name we can't match still shows, unlinked).
function PlayerChip({ player, name, badge }) {
  const label = player?.last_name || name;
  const initials = label.replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase();
  const body = (
    <>
      <span className="lineup-chip-photo-wrap">
        {player?.headshot_url
          ? <img className="lineup-chip-photo" src={player.headshot_url} alt="" loading="lazy" />
          : <span className="lineup-chip-photo lineup-chip-initials" aria-hidden="true">{initials}</span>}
        {player?.sweater_number != null && <span className="lineup-chip-number" aria-label={`number ${player.sweater_number}`}>{player.sweater_number}</span>}
      </span>
      <span className="lineup-chip-name">{label}</span>
      {badge && <span className="lineup-chip-badge">{badge}</span>}
    </>
  );
  return player
    ? <Link className="lineup-chip" to={`/players/${player.player_id}`}>{body}</Link>
    : <span className="lineup-chip">{body}</span>;
}

function Group({ title, label, columns, rows }) {
  if (!rows.length) return null;
  const width = Math.max(...rows.map((r) => r.players.length), columns.length);
  return (
    <section className="lineup-group" aria-label={title} style={{ "--cols": width }}>
      <h4 className="lineup-group-title">{title}</h4>
      {columns.length > 0 && (
        <div className="lineup-cols" aria-hidden="true">
          <span />
          {columns.map((c) => <span key={c}>{c}</span>)}
        </div>
      )}
      <ol className="lineup-rows" aria-label={label}>
        {rows.map((row) => (
          <li key={row.key} className="lineup-row">
            <span className="lineup-row-label">{row.label}</span>
            {row.players.map((p) => <PlayerChip key={p.key} player={p.player} name={p.name} badge={p.badge} />)}
          </li>
        ))}
      </ol>
    </section>
  );
}

// A team's lineup as a depth chart: forward lines (LW, C, RW), defense
// pairs (LD, RD), and goalies, each player a chip with his headshot.
// Lines are [{ players: [{ player, name }] }], best first; `team` names the
// lists for screen readers ("PIT forward lines").
export default function LineupGrid({ team, forwards = [], defense = [], goalies = [] }) {
  const rows = (lines, prefix) => lines.map((line, i) => ({
    key: `${prefix}${i}`,
    label: line.players.length === 1 && prefix === "D" ? "7D" : i + 1,
    players: line.players.map((p, j) => ({ ...p, key: `${p.player?.player_id ?? p.name}-${j}` })),
  }));
  const goalieRow = goalies.length
    ? [{ key: "G", label: "G", players: goalies.map((g, i) => ({ ...g, key: `${g.player?.player_id ?? g.name}-${i}`, badge: i === 0 ? g.badge : null })) }]
    : [];
  return (
    <div className="lineup-grid">
      <Group title="Forwards" label={`${team} forward lines`} columns={["LW", "C", "RW"]} rows={rows(forwards, "L")} />
      <Group title="Defense" label={`${team} defense pairs`} columns={["LD", "RD"]} rows={rows(defense, "D")} />
      <Group title="Goalies" label={`${team} goalies`} columns={[]} rows={goalieRow} />
    </div>
  );
}
