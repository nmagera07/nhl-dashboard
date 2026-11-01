import ShareButton from "./ShareButton.jsx";
import { API_BASE } from "../config.js";
import { betId, betLabel } from "../utils/myBets.js";
import { formatEv, formatPct, formatPrice } from "../utils/odds.js";

const units = (u) => `${u >= 0 ? "+" : "−"}${Math.abs(u).toFixed(2)}u`;
const OUTCOME = { win: "Won", loss: "Lost", push: "Push" };
const NOT_STARTED = new Set(["FUT", "PRE"]);

const VALUE_AT = 0.02; // value_pick.py: a pick is value at +2% expected return or more

// The season's record of these picks: three numbers, then the last pick.
function Record({ record, last }) {
  if (!record?.nights) return null;
  return (
    <>
      <dl className="votn-stats">
        <div><dt>Season</dt><dd>{record.wins}-{record.losses}{record.pushes ? `-${record.pushes}` : ""}</dd></div>
        <div><dt>Units</dt><dd>{units(record.units)}</dd></div>
        {record.clv_count > 0 && <div><dt>Beat the close</dt><dd>{record.beat_close}/{record.clv_count}</dd></div>}
      </dl>
      {last?.result && (
        <p className="votn-last">Last pick: {betLabel(last.pick)} {formatPrice(last.pick.price)}, {OUTCOME[last.result.outcome].toLowerCase()}.</p>
      )}
    </>
  );
}

const startTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// The top of the Bets tab: the night's best value bet from the morning lines
// (value_pick.py), or the closest one when nothing clears the bar, with a
// meter of its expected return against the +2% value bar and the season's
// record of these picks. Tap Track to add it to My bets.
export default function ValueOfTheNight({ data, game, today, tracked, onTrack }) {
  if (!data?.available) return null;
  const p = data.pick;
  const open = !game || NOT_STARTED.has(game.gameState);
  const id = betId(p.game_id, p.market, p.side);
  const isTracked = tracked.has(id);
  const track = () => onTrack({
    id, gameId: p.game_id, date: today, away: p.away, home: p.home, market: p.market, side: p.side,
    line: p.line, price: p.price, placedAt: new Date().toISOString(),
  });
  // How far the expected return gets toward the value bar (full at +2%).
  const meter = Math.max(0, Math.min(1, p.ev / VALUE_AT));
  return (
    <section className={p.value ? "votn votn-value" : "votn"} aria-label={p.value ? "Value of the night" : "Closest to value tonight"}>
      <p className="votn-kicker">{p.value ? "Value of the night" : "Closest to value tonight"}</p>
      <p className="votn-bet">
        <span>{betLabel(p)}</span> <span className="votn-price">{formatPrice(p.price)}</span>
      </p>
      <p className="votn-where">
        {p.market === "puck_line" ? "Puck line" : "To win"}{p.book && ` · best at ${p.book}`} · {p.away} @ {p.home}
        {game?.startTimeUTC && open ? `, ${startTime(game.startTimeUTC)}` : ""}
      </p>
      <div className="votn-meter" role="img" aria-label={`Expected return ${formatEv(p.ev)}; value starts at +2%`}>
        <span style={{ width: `${Math.round(meter * 100)}%` }} />
      </div>
      <p className="votn-meter-labels"><span><strong>{formatEv(p.ev)}</strong> expected return</span><span>value at +2%</span></p>
      <p className="votn-why">
        Fair chance {formatPct(p.ours)} vs. the books&apos; {formatPct(p.market_prob)}.
        {!p.value && " Nothing cleared the value bar tonight; this is the closest."}
        {" "}Picked from the morning lines.
      </p>
      {data.result && <p className="votn-why">Result: {OUTCOME[data.result.outcome]} {units(data.result.units)}.</p>}
      <Record record={data.record} last={data.last} />
      <div className="votn-actions">
        {open && (
          <button type="button" className={isTracked ? "votn-track votn-tracked" : "votn-track"} aria-pressed={isTracked} onClick={track}>
            {isTracked ? "✓ Tracking" : "Track"}
          </button>
        )}
        <ShareButton url={`https://puckpulse.io/v/${data.date}`} image={`${API_BASE}/og/value/${data.date}.png`}
                     title={`PuckPulse's ${p.value ? "value of the night" : "closest to value tonight"}: ${betLabel(p)} ${formatPrice(p.price)}`}
                     event="share-value" label="Share" />
      </div>
    </section>
  );
}
