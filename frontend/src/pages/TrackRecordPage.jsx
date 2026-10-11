import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";

// Below this many graded games, the numbers swing too much to read much into.
const SMALL_SAMPLE = 100;

const pct = (v) => `${Math.round(v * 100)}%`;

function shortDate(iso) {
  // Noon local time, so the date never shifts across a timezone boundary.
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function Tile({ label, value, detail }) {
  return (
    <div className="record-tile">
      <span className="record-tile-label">{label}</span>
      <strong className="record-tile-value">{value}</strong>
      <span className="record-tile-detail">{detail}</span>
    </div>
  );
}

function Calibration({ buckets }) {
  return (
    <section className="race-card" aria-labelledby="calibration-title">
      <div className="race-card-header">
        <h2 id="calibration-title">Does it mean what it says?</h2>
      </div>
      <p className="record-intro">
        Games grouped by how confident the model was in its favorite. If the model is honest, the bar
        (how often the favorite won) ends near the marker (what the model said).
      </p>
      <ul className="calibration-list">
        {buckets.map((b) => (
          <li key={b.label} className="calibration-row">
            <span className="calibration-label">{b.label}</span>
            <div className="calibration-bar" role="img"
              aria-label={`Said ${pct(b.predicted)}, favorite won ${pct(b.actual)} of ${b.games} games`}>
              <span className="calibration-fill" style={{ width: pct(b.actual) }} />
              <span className="calibration-marker" style={{ left: pct(b.predicted) }} />
            </div>
            <span className="calibration-detail">
              Said {pct(b.predicted)} · won {pct(b.actual)} · {b.games} {b.games === 1 ? "game" : "games"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecentPicks({ games }) {
  return (
    <section className="race-card" aria-labelledby="recent-picks-title">
      <div className="race-card-header">
        <h2 id="recent-picks-title">Recent picks</h2>
      </div>
      <ul className="pick-list">
        {games.map((g) => {
          const homeFavored = g.home_win_prob > 0.5;
          const tossUp = g.home_win_prob === 0.5;
          const pick = tossUp ? "Toss-up" : `${homeFavored ? g.home : g.away} ${pct(homeFavored ? g.home_win_prob : 1 - g.home_win_prob)}`;
          const mark = g.favorite_won == null ? "–" : g.favorite_won ? "✓" : "✗";
          const result = g.favorite_won == null ? "no pick" : g.favorite_won ? "right" : "wrong";
          return (
            <li key={g.game_id}>
              <Link className="pick-row" to={`/games/${g.game_id}`}>
                <span className="pick-date">{shortDate(g.game_date)}</span>
                <span className="pick-game">
                  {g.away} {g.away_score}, {g.home} {g.home_score}{g.ended && g.ended !== "REG" ? ` (${g.ended})` : ""}
                </span>
                <span className="pick-call">{pick}</span>
                <span className={`pick-mark pick-mark-${result.replace(" ", "-")}`} aria-label={result}>{mark}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function TrackRecordPage() {
  const { data, status } = useFetchWithStatus(`${API_BASE}/predictions/track-record`);
  const loaded = status === "ready" && data && typeof data.games === "number";

  return (
    <main className="track-record-page">
      <div className="page-header page">
        <h1>Model track record</h1>
        <span className="page-subtitle">How PuckPulse&apos;s game predictions have done this season</span>
      </div>

      {status === "loading" && <p className="status-line">Loading the track record…</p>}
      {(status === "error" || (status === "ready" && !loaded)) && (
        <p className="status-line status-error">Couldn&apos;t load the track record.</p>
      )}

      {loaded && data.games === 0 && (
        <p className="race-empty">No graded games yet. Predictions are scored the morning after each game.</p>
      )}

      {loaded && data.games > 0 && (
        <>
          <div className="record-tiles">
            <Tile label="Favorite won" value={data.favorite_won == null ? "—" : pct(data.favorite_won)}
              detail={`${data.favorite_correct} of ${data.picks} games`} />
            <Tile label="Brier score" value={data.brier.toFixed(3)}
              detail={`Coin flip: ${data.coin_flip_brier.toFixed(3)} · lower is better`} />
            <Tile label="Games graded" value={data.games}
              detail={data.pending ? `${data.pending} waiting on results` : "All caught up"} />
          </div>

          {data.games < SMALL_SAMPLE && (
            <p className="record-sample-note">
              Early days: with only {data.games} games, these numbers can swing a lot. Single hockey games are close
              to coin flips, so even a great model's favorites win only about 60% of the time.
            </p>
          )}

          {data.calibration.length > 0 && <Calibration buckets={data.calibration} />}
          {data.recent.length > 0 && <RecentPicks games={data.recent} />}
        </>
      )}

      <section className="race-card record-how" aria-labelledby="record-how-title">
        <div className="race-card-header">
          <h2 id="record-how-title">How this works</h2>
        </div>
        <ul>
          <li>Every morning, before any puck drops, PuckPulse saves the model&apos;s win probability for each game that day.</li>
          <li>Saved predictions are never changed. After each game, it&apos;s graded automatically.</li>
          <li>
            <strong>Brier score</strong> measures how close the probabilities were to what happened. Always saying
            50/50 scores 0.250. Good hockey models usually land around 0.23–0.24.
          </li>
          <li>The model rates teams on goals and expected goals, plus home ice. The same model drives the playoff odds.</li>
          <li>For fun and insight, not betting advice.</li>
        </ul>
      </section>
      <p className="data-credit">
        Expected goals (xG) courtesy of <a href="https://moneypuck.com" target="_blank" rel="noreferrer">MoneyPuck.com</a>.
      </p>
    </main>
  );
}
