import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { API_BASE } from "../config.js";
import { cutLine, makeRng, simulateSeason } from "../utils/seasonSim.js";
import { formatOdds } from "../utils/playoffRace.js";

const SPREAD_RUNS = 3000;
const CHUNK = 150; // seasons per slice, so the page stays responsive while the spread builds
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const shortDate = (iso) => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

function ordinal(n) {
  const suffixes = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0]);
}

const possessive = (name) => (name.endsWith("s") ? `${name}'` : `${name}'s`);

function seedLabel(seed, division) {
  if (!seed) return null;
  return seed.startsWith("WC") ? `Wild card ${seed.slice(2)}` : `${ordinal(Number(seed.slice(1)))} in the ${division}`;
}

function useSimInputs() {
  const [state, setState] = useState({ status: "loading", inputs: null });
  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/season-sim`)
      .then((res) => (res.status === 404 ? null : res.ok ? res.json() : Promise.reject(new Error(res.status))))
      .then((inputs) => active && setState({ status: inputs ? "ready" : "empty", inputs }))
      .catch(() => active && setState({ status: "error", inputs: null }));
    return () => {
      active = false;
    };
  }, []);
  return state;
}

// Thousands of seasons for one team, run in slices so the histogram fills
// in live instead of freezing the page.
function useSpread(inputs, team, enabled) {
  const [spread, setSpread] = useState(null);
  useEffect(() => {
    if (!enabled || !inputs) return undefined;
    let cancelled = false;
    const rng = makeRng();
    const counts = {};
    let runs = 0;
    let playoffs = 0;
    const step = () => {
      if (cancelled) return;
      for (let i = 0; i < CHUNK && runs < SPREAD_RUNS; i++, runs++) {
        const { records, picture } = simulateSeason(inputs, rng);
        const pts = records[team].points;
        counts[pts] = (counts[pts] || 0) + 1;
        if (picture[team].seed) playoffs += 1;
      }
      setSpread({ runs, counts: { ...counts }, playoffPct: playoffs / runs, done: runs >= SPREAD_RUNS });
      if (runs < SPREAD_RUNS) setTimeout(step, 0);
    };
    setTimeout(step, 0);
    return () => {
      cancelled = true;
    };
  }, [inputs, team, enabled]);
  return spread;
}

function percentile(counts, q) {
  const entries = Object.entries(counts).map(([p, n]) => [Number(p), n]).sort((a, b) => a[0] - b[0]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  let seen = 0;
  for (const [p, n] of entries) {
    seen += n;
    if (seen >= q * total) return p;
  }
  return entries.at(-1)?.[0];
}

function Histogram({ counts, mark }) {
  const points = Object.keys(counts).map(Number);
  if (!points.length) return null;
  const lo = Math.min(...points, mark ?? Infinity);
  const hi = Math.max(...points, mark ?? -Infinity);
  const max = Math.max(...Object.values(counts));
  const width = 100 / (hi - lo + 1);
  return (
    <div className="sim-histogram" aria-hidden="true">
      <div className="sim-histogram-bars">
        {Array.from({ length: hi - lo + 1 }, (_, i) => {
          const p = lo + i;
          return (
            <span
              key={p}
              className={p === mark ? "sim-bar sim-bar-mark" : "sim-bar"}
              style={{ left: `${i * width}%`, width: `${width}%`, height: `${((counts[p] || 0) / max) * 100}%` }}
            />
          );
        })}
      </div>
      <div className="sim-histogram-axis">
        <span>{lo} pts</span>
        <span>{hi} pts</span>
      </div>
    </div>
  );
}

// "Sim the season": plays out the rest of the regular season in the
// browser with the playoff-odds model. Each click is one possible season;
// thousands more run in the background to show the likely range.
function SeasonSimulator({ team }) {
  const abbrev = team.team_abbrev;
  const { status, inputs } = useSimInputs();
  const [run, setRun] = useState(null);
  const [tally, setTally] = useState({ runs: 0, playoffs: 0 });
  const rngRef = useRef(null);
  const sectionRef = useRef(null);
  const location = useLocation();
  const spread = useSpread(inputs, abbrev, run != null);

  // Arriving from the My team card's "Sim the season" link.
  useEffect(() => {
    if (location.hash === "#season-sim" && status === "ready") sectionRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [location.hash, status]);

  const known = inputs?.teams?.[abbrev];
  const gamesLeft = inputs ? inputs.games.filter(([, h, a]) => h === abbrev || a === abbrev).length : 0;

  const simulate = () => {
    rngRef.current ||= makeRng();
    const result = simulateSeason(inputs, rngRef.current, abbrev);
    const record = result.records[abbrev];
    const seed = result.picture[abbrev].seed;
    setRun({
      record,
      seed,
      divisionRank: result.picture[abbrev].divisionRank,
      missedBy: seed ? null : cutLine(result, abbrev) - record.points,
      log: result.log,
    });
    setTally((t) => ({ runs: t.runs + 1, playoffs: t.playoffs + (seed ? 1 : 0) }));
  };

  return (
    <section className="season-sim" id="season-sim" ref={sectionRef} aria-labelledby="season-sim-title">
      <div className="season-sim-header">
        <div>
          <h2 id="season-sim-title">Season simulator</h2>
          <p>
            {status === "ready" && known
              ? `Play out the ${possessive(team.common_name || abbrev)} last ${gamesLeft} games (and everyone else's) with the playoff odds model.`
              : "Play out the rest of the season with the playoff odds model."}
          </p>
        </div>
        {status === "ready" && known && (
          <button type="button" className="sim-button" onClick={simulate}>
            {run ? "Sim again" : "Sim the season"}
          </button>
        )}
      </div>

      {status === "loading" && <p className="sim-note">Loading the model…</p>}
      {status === "error" && <p className="sim-note status-error">Couldn't load the simulator.</p>}
      {(status === "empty" || (status === "ready" && !known)) && (
        <p className="sim-note">The simulator updates after each morning's playoff odds run.</p>
      )}

      {run && (
        <div className="sim-result" aria-live="polite">
          <div className="sim-final">
            <div>
              <span className="sim-kicker">Final record</span>
              <strong className="sim-record">{run.record.wins}-{run.record.losses}-{run.record.ot_losses}</strong>
              <span className="sim-points">{run.record.points} PTS · {ordinal(run.divisionRank)} in the {known.division}</span>
            </div>
            <span className={run.seed ? "sim-outcome sim-outcome-in" : "sim-outcome sim-outcome-out"}>
              {run.seed
                ? `Playoffs · ${seedLabel(run.seed, known.division)}`
                : `Missed by ${run.missedBy} pt${run.missedBy === 1 ? "" : "s"}`}
            </span>
          </div>

          <ol className="sim-games" aria-label="Simulated results, game by game">
            {run.log.map((g, i) => (
              <li
                key={`${g.date}-${i}`}
                className={`sim-game sim-game-${g.result.toLowerCase()}`}
                title={`${shortDate(g.date)} ${g.home ? "vs" : "@"} ${g.opponent}: ${g.result === "OTL" ? `L (${g.decided})` : g.decided === "REG" ? g.result : `${g.result} (${g.decided})`}`}
              />
            ))}
          </ol>
          <p className="sim-legend">
            <span className="sim-key sim-game-w" /> Win <span className="sim-key sim-game-otl" /> OT/SO loss <span className="sim-key sim-game-l" /> Loss
            <span className="sim-tally">Your sims: {tally.runs} · playoffs in {tally.playoffs}</span>
          </p>

          {spread && (
            <div className="sim-spread">
              <p>
                {spread.done ? `Across ${spread.runs.toLocaleString()} seasons` : `Simulating… ${spread.runs.toLocaleString()} seasons`}:{" "}
                <strong>{percentile(spread.counts, 0.5)} PTS</strong> typical, 80% between {percentile(spread.counts, 0.1)} and{" "}
                {percentile(spread.counts, 0.9)} · playoffs <strong>{formatOdds(spread.playoffPct)}</strong>
              </p>
              <Histogram counts={spread.counts} mark={run.record.points} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default SeasonSimulator;
