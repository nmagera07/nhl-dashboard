import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import PlayerPicker from "../components/PlayerPicker.jsx";

const fullSeason = (id) => `${String(id).slice(0, 4)}-${String(id).slice(6)}`;
const validId = (v) => (/^\d{6,10}$/.test(v || "") ? v : null);
const validSeason = (v) => (/^\d{8}$/.test(v || "") ? v : null);

// 10,000 simulated seasons as bars; the likely range (10th-90th percentile) highlighted.
function Histogram({ bins, width, low, high, label }) {
  const W = 320;
  const H = 90;
  const max = Math.max(...bins.map(([, n]) => n));
  const barW = W / bins.length;
  return (
    <svg className="tm-histogram" viewBox={`0 0 ${W} ${H + 18}`} role="img" aria-label={label}>
      {bins.map(([from, n], i) => {
        const inRange = from + width > low && from <= high;
        const h = Math.max(1, (n / max) * H);
        return <rect key={from} x={i * barW + 1} y={H - h} width={barW - 2} height={h} rx="2" className={inRange ? "tm-bar tm-bar-in" : "tm-bar"} />;
      })}
      <text x="0" y={H + 14} className="tm-axis">{bins[0][0]}</text>
      <text x={W} y={H + 14} textAnchor="end" className="tm-axis">{bins[bins.length - 1][0] + width - 1}</text>
    </svg>
  );
}

// "What if?": one of a skater's seasons replayed at another era's scoring
// (backend time_machine.py, GET /players/{id}/time-machine).
export default function TimeMachinePage() {
  const [params, setParams] = useSearchParams();
  const player = validId(params.get("player"));
  const season = validSeason(params.get("season"));
  const target = validSeason(params.get("target"));
  const { data: era } = useFetchWithStatus(`${API_BASE}/era/scoring`);
  const query = new URLSearchParams({ ...(season ? { season } : {}), ...(target ? { target } : {}) }).toString();
  const { data, status } = useFetchWithStatus(player ? `${API_BASE}/players/${player}/time-machine${query ? `?${query}` : ""}` : null);

  const set = (changes) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, String(v));
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  const name = data?.player?.name; // a 400 comes back as { detail }
  useEffect(() => {
    document.title = name ? `${name} in another era | PuckPulse` : "Time machine | PuckPulse";
  }, [name]);

  const seasons = era ? Object.keys(era.seasons).sort().reverse() : [];
  const ref = era?.reference_season;
  const s = data?.source;
  const t = data?.target;

  return (
    <main className="page time-machine">
      <div className="page-header"><h1>Time machine</h1></div>
      <p className="page-subtitle">Take a player&apos;s season and play it in another era: today&apos;s game, or any season back to 1917.</p>

      {!player || params.get("pick") ? (
        <section className="tm-card"><PlayerPicker label="Player" autoFocus onPick={(id) => set({ player: id, season: null, pick: null })} /></section>
      ) : status === "error" || data?.detail ? (
        <p className="status-error">
          {typeof data?.detail === "string" ? data.detail : "Couldn't run that one."}{" "}
          <button type="button" className="link-button" onClick={() => set({ pick: "1" })}>Pick someone else</button>
        </p>
      ) : !data ? (
        <p className="muted">Firing up the time machine…</p>
      ) : (
        <>
          <section className="tm-card tm-controls">
            <div className="tm-who">
              {data.player.headshot && <img src={data.player.headshot} alt="" />}
              <Link to={`/players/${data.player.id}`}>{name}</Link>
              <button type="button" onClick={() => set({ pick: "1" })}>Change</button>
            </div>
            <label>
              His season
              <select value={s.season_id} onChange={(e) => set({ season: e.target.value })}>
                {[...data.seasons].reverse().map((id) => <option key={id} value={id}>{fullSeason(id)}</option>)}
              </select>
            </label>
            <label>
              Play it in
              <select value={t.season_id} onChange={(e) => set({ target: e.target.value === String(ref) ? null : e.target.value })}>
                {seasons.map((id) => (
                  <option key={id} value={id}>{Number(id) === ref ? `Today (${fullSeason(id)})` : fullSeason(id)} · {era.seasons[id].toFixed(2)} goals/game</option>
                ))}
              </select>
            </label>
          </section>

          <section className="tm-card tm-result" aria-live="polite">
            <p className="tm-eyebrow">{name}&apos;s {fullSeason(s.season_id)} in {Number(t.season_id) === ref ? "today's game" : fullSeason(t.season_id)}</p>
            <p className="tm-big"><strong>~{data.points.median}</strong> points</p>
            <p className="tm-range">likely {data.points.low}–{data.points.high} over 82 games · {data.goals.median} goals, {data.assists.median} assists</p>
            <Histogram bins={data.histogram} width={data.bin_width} low={data.points.low} high={data.points.high}
                       label={`Points over 10,000 simulated seasons: most between ${data.points.low} and ${data.points.high}`} />
            <p className="tm-real">
              His real {fullSeason(s.season_id)}: {s.goals} G, {s.assists} A, <strong>{s.points} points</strong> in {s.games_played} games,
              when teams scored {s.scoring.toFixed(2)} a game. In {fullSeason(t.season_id)} scoring ({t.scoring.toFixed(2)}),
              each of his points counts ×{data.factor.toFixed(2)}.
            </p>
          </section>
          <p className="compare-note">
            How it works: his goals and assists per game, rescaled by league scoring, then 10,000 simulated 82-game seasons
            with room for the translation to be off. It&apos;s for fun: it can&apos;t know how he&apos;d adapt to another era&apos;s rules,
            equipment, or goalies.
          </p>
        </>
      )}
    </main>
  );
}
