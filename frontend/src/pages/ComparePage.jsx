import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import PlayerPicker from "../components/PlayerPicker.jsx";
import { compareRows, eraAdjust, isGoalie, winner } from "../utils/compare.js";
import { formatSeasonLabel } from "../utils/formatSeasonLabel.js";

const POSITIONS = { C: "Center", L: "Left Wing", R: "Right Wing", D: "Defense", G: "Goalie" };
const validId = (v) => (/^\d{6,10}$/.test(v || "") ? v : null);

// One side of the comparison: who he is, or a picker until he's chosen.
function Side({ slot, player, status, onPick, onClear }) {
  const [changing, setChanging] = useState(false);
  if (!player || changing) {
    return (
      <div className="compare-side compare-side-empty">
        {status === "loading" && !changing ? <p className="muted">Loading…</p> : (
          <PlayerPicker label={`Player ${slot === "a" ? "1" : "2"}`} autoFocus={changing || slot === "b"}
                        onPick={(id) => { setChanging(false); onPick(id); }} />
        )}
        {status === "error" && !changing && <p className="status-error">Couldn't load that player.</p>}
      </div>
    );
  }
  const name = `${player.first_name} ${player.last_name}`;
  const where = player.team_abbrev || (player.status === "retired" ? `Retired · last played ${formatSeasonLabel(player.last_season_id)}` : "Not on a roster");
  return (
    <div className="compare-side">
      {player.headshot_url && <img className="compare-headshot" src={player.headshot_url} alt="" />}
      <Link className="compare-name" to={`/players/${player.player_id}`}>{name}</Link>
      <span className="compare-meta">{POSITIONS[player.position_code] || player.position_code} · {where}</span>
      {player.in_hall_of_fame && <span className="player-hof">Hall of Fame</span>}
      <span className="compare-side-actions">
        <button type="button" onClick={() => setChanging(true)}>Change</button>
        <button type="button" onClick={onClear} aria-label={`Remove ${name}`}>✕</button>
      </span>
    </div>
  );
}

// Two players side by side, current or retired: career, playoffs, best
// season, and this season, with the better number in each row marked.
export default function ComparePage() {
  const [params, setParams] = useSearchParams();
  const ids = { a: validId(params.get("a")), b: validId(params.get("b")) };
  const a = useFetchWithStatus(ids.a ? `${API_BASE}/players/${ids.a}` : null);
  const b = useFetchWithStatus(ids.b ? `${API_BASE}/players/${ids.b}` : null);
  const pa = ids.a && a.status === "ready" ? a.data : null;
  const pb = ids.b && b.status === "ready" ? b.data : null;
  const { data: era } = useFetchWithStatus(`${API_BASE}/era/scoring`);
  const eraOn = params.get("era") === "1";

  const setEra = (on) => {
    const next = new URLSearchParams(params);
    if (on) next.set("era", "1");
    else next.delete("era");
    setParams(next, { replace: true });
  };

  const setSlot = (slot, id) => {
    const next = new URLSearchParams(params);
    if (id) next.set(slot, String(id));
    else next.delete(slot);
    setParams(next, { replace: true });
  };

  const names = [pa, pb].filter(Boolean).map((p) => p.last_name);
  useEffect(() => {
    document.title = names.length === 2 ? `${names[0]} vs ${names[1]} | PuckPulse` : "Compare players | PuckPulse";
  }, [names[0], names[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  const mismatch = pa && pb && isGoalie(pa) !== isGoalie(pb);
  const goalies = pa && pb && isGoalie(pa) && isGoalie(pb);
  const adjusted = eraOn && era && !goalies;
  const rows = pa && pb && !mismatch
    ? (adjusted ? compareRows(eraAdjust(pa, era), eraAdjust(pb, era)) : compareRows(pa, pb))
    : [];
  const refLabel = era ? formatSeasonLabel(era.reference_season) : "";
  const sections = [...new Set(rows.map((r) => r.section))];

  return (
    <main className="page compare-page">
      <div className="page-header"><h1>Compare players</h1></div>
      <p className="page-subtitle">Any two NHL players, today's or all-time. Pick two skaters or two goalies.</p>
      <div className="compare-sides">
        <Side slot="a" player={pa} status={ids.a ? a.status : "idle"} onPick={(id) => setSlot("a", id)} onClear={() => setSlot("a", null)} />
        <span className="compare-vs" aria-hidden="true">vs</span>
        <Side slot="b" player={pb} status={ids.b ? b.status : "idle"} onPick={(id) => setSlot("b", id)} onClear={() => setSlot("b", null)} />
      </div>
      {mismatch && <p className="compare-note">Pick two skaters or two goalies: their numbers don't compare.</p>}
      {pa && pb && !mismatch && !goalies && era && (
        <div className="compare-era">
          <div className="view-toggle" role="group" aria-label="Numbers">
            {[[false, "Raw"], [true, "Era-adjusted"]].map(([on, label]) => (
              <button key={label} type="button" aria-pressed={eraOn === on}
                      className={eraOn === on ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"} onClick={() => setEra(on)}>
                {label}
              </button>
            ))}
          </div>
          {adjusted && (
            <p className="compare-era-note">
              Every season rescaled to {refLabel} scoring ({era.reference.toFixed(2)} goals per team per game). League scoring has
              ranged from 1.46 (1928-29) to 4.79 (1919-20), so a point meant more in some eras than others.
            </p>
          )}
        </div>
      )}
      {sections.map((section) => (
        <section key={section} className="compare-card">
          <h2 className="compare-card-head">
            <span>{pa.last_name}</span>{section}<span>{pb.last_name}</span>
          </h2>
          {rows.filter((r) => r.section === section).map((r) => {
            const win = winner(r);
            return (
              <div key={r.label} className="compare-row">
                <span className={win === "a" ? "compare-value compare-win" : "compare-value"}>{r.a == null ? "—" : r.show(r.a)}</span>
                <span className="compare-label">{r.label}</span>
                <span className={win === "b" ? "compare-value compare-win" : "compare-value"}>{r.b == null ? "—" : r.show(r.b)}</span>
              </div>
            );
          })}
        </section>
      ))}
      {rows.length > 0 && !adjusted && !goalies && (
        <p className="compare-note">
          Raw numbers from different eras aren&apos;t a fair fight: goals were easier to come by in some decades. Try Era-adjusted.
        </p>
      )}
      {goalies && <p className="compare-note">Goalie numbers are raw: era adjustment for goalies is coming.</p>}
    </main>
  );
}
