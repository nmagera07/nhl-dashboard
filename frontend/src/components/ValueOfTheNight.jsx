import ShareButton from "./ShareButton.jsx";
import { API_BASE } from "../config.js";
import { betId, betLabel } from "../utils/myBets.js";
import { formatEv, formatPct, formatPrice } from "../utils/odds.js";

const units = (u) => `${u >= 0 ? "+" : "−"}${Math.abs(u).toFixed(2)}u`;
const OUTCOME = { win: "Won", loss: "Lost", push: "Push" };
const NOT_STARTED = new Set(["FUT", "PRE"]);

function Record({ record, last }) {
  if (!record?.nights) return null;
  return (
    <p className="votn-record">
      This season: <strong>{record.wins}-{record.losses}{record.pushes ? `-${record.pushes}` : ""}</strong>, {units(record.units)}
      {record.clv_count > 0 && <>, beat the closing line {record.beat_close} of {record.clv_count}</>}.
      {last?.result && <> Last pick: {betLabel(last.pick)} {formatPrice(last.pick.price)}, {OUTCOME[last.result.outcome].toLowerCase()}.</>}
    </p>
  );
}

// The top of the Bets tab: the night's best value bet from the morning lines
// (value_pick.py), or the closest one when nothing clears the bar, with the
// season's record of these picks. Tap Track to add it to My bets.
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
  return (
    <section className={p.value ? "votn votn-value" : "votn"} aria-label={p.value ? "Value of the night" : "Closest to value tonight"}>
      <p className="votn-kicker">{p.value ? "Value of the night" : "Closest to value tonight"}</p>
      <div className="votn-main">
        <div>
          <p className="votn-bet">
            {betLabel(p)} <span className="votn-price">{formatPrice(p.price)}</span>
            {p.book && <span className="votn-book"> {p.book}</span>}
          </p>
          <p className="votn-game">{p.away} @ {p.home} · {p.market === "puck_line" ? "puck line" : "to win"}</p>
        </div>
        {open && (
          <button type="button" className={isTracked ? "votn-track votn-tracked" : "votn-track"} aria-pressed={isTracked} onClick={track}>
            {isTracked ? "✓ Tracking" : "Track"}
          </button>
        )}
      </div>
      <p className="votn-why">
        PuckPulse {formatPct(p.ours)} vs. the books&apos; {formatPct(p.market_prob)}: expected return {formatEv(p.ev)} at this price.
        {!p.value && " Nothing cleared the value bar tonight; this is the closest."}
        {" "}Picked from the morning lines.
      </p>
      {data.result && <p className="votn-why">Result: {OUTCOME[data.result.outcome]} {units(data.result.units)}.</p>}
      <Record record={data.record} last={data.last} />
      <div className="votn-share">
        <ShareButton url={`https://puckpulse.io/v/${data.date}`} image={`${API_BASE}/og/value/${data.date}.png`}
                     title={`PuckPulse's ${p.value ? "value of the night" : "closest to value tonight"}: ${betLabel(p)} ${formatPrice(p.price)}`}
                     event="share-value" label="Share" />
      </div>
    </section>
  );
}
