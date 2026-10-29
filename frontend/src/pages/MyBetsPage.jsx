import { useEffect } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useMyBets } from "../hooks/useMyBets.js";
import { relativeDayLabel, todayISO } from "../utils/dates.js";
import { betLabel, grade, summarize } from "../utils/myBets.js";
import { formatEv, formatPrice } from "../utils/odds.js";

const units = (u) => `${u >= 0 ? "+" : "−"}${Math.abs(u).toFixed(2)}u`;
const OUTCOME = { win: "Won", loss: "Lost", push: "Push" };

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

// Grades the bets still open on each past or current day: that day's
// scores and closing lines. Returns {betId: result} for the finished games.
async function gradeOpenBets(bets, today) {
  const days = [...new Set(bets.filter((b) => !b.result && b.date <= today).map((b) => b.date))];
  const results = {};
  await Promise.all(days.map(async (day) => {
    try {
      const [scores, lines] = await Promise.all([getJSON(`${API_BASE}/games/date/${day}`), getJSON(`${API_BASE}/bets?date=${day}`)]);
      for (const bet of bets.filter((b) => !b.result && b.date === day)) {
        const game = (scores.games || []).find((g) => g.id === bet.gameId);
        const result = grade(bet, game, lines.games?.[String(bet.gameId)]);
        if (result) results[bet.id] = result;
      }
    } catch {
      // try again next visit
    }
  }));
  return results;
}

function Summary({ bets }) {
  const s = summarize(bets);
  if (!s.graded) return null;
  return (
    <section className="pickem-card my-bets-summary">
      <div className="rc-tile-row">
        <div className="rc-tile"><strong>{s.wins}-{s.losses}{s.pushes ? `-${s.pushes}` : ""}</strong><span>record</span></div>
        <div className="rc-tile">
          <strong className={s.units > 0 ? "rc-right" : s.units < 0 ? "rc-wrong" : ""}>{units(s.units)}</strong>
          <span>{formatEv(s.roi)} per bet</span>
        </div>
      </div>
      {s.clvCount > 0 && (
        <p className="my-bets-clv">
          Beat the closing line on <strong>{s.beatClose} of {s.clvCount}</strong> (average {formatEv(s.clv)}).
          Winning bets can be luck; beating the close over time is the sign of a good bettor.
        </p>
      )}
    </section>
  );
}

function BetRow({ bet, onRemove }) {
  const r = bet.result;
  return (
    <li className="my-bets-row">
      <div className="my-bets-main">
        <span className="my-bets-bet">{betLabel(bet)} <span className="my-bets-price">{formatPrice(bet.price)}</span></span>
        <Link className="my-bets-game" to={`/games/${bet.gameId}`}>{bet.away} @ {bet.home} · {relativeDayLabel(bet.date)}</Link>
        {r?.clv != null && (
          <span className={r.clv > 0 ? "my-bets-clv-line rc-right" : "my-bets-clv-line"}>
            {formatEv(r.clv)} vs. the close{r.closePrice != null ? ` (${formatPrice(r.closePrice)})` : ""}
          </span>
        )}
      </div>
      <div className="my-bets-side">
        {r ? (
          <span className={`my-bets-result my-bets-${r.outcome}`}>{OUTCOME[r.outcome]} {units(r.units)}</span>
        ) : (
          <span className="my-bets-result">Open</span>
        )}
        <button type="button" className="my-bets-remove" onClick={() => onRemove(bet.id)} aria-label={`Remove ${betLabel(bet)}, ${bet.away} @ ${bet.home}`}>Remove</button>
      </div>
    </li>
  );
}

// My bets: the bets tracked from the Bets tab (in this browser), graded
// after each game, with the record, units, and closing-line value.
export default function MyBetsPage() {
  const { bets, remove, record } = useMyBets();
  const today = todayISO();
  const openKey = bets.filter((b) => !b.result).map((b) => b.id).join(",");

  useEffect(() => {
    if (!openKey) return;
    let live = true;
    gradeOpenBets(bets, today).then((results) => {
      if (live && Object.keys(results).length) record(results);
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- regrade when the open bets change, not on every save
  }, [openKey, today, record]);

  const newestFirst = [...bets].sort((a, b) => b.date.localeCompare(a.date) || b.placedAt.localeCompare(a.placedAt));
  const open = newestFirst.filter((b) => !b.result);
  const graded = newestFirst.filter((b) => b.result);

  return (
    <main className="page my-bets-page">
      <div className="page-header"><h1>My bets</h1></div>
      <p className="page-subtitle">
        Bets you tap on the <Link className="accent-link" to="/bets">Bets tab</Link>, 1 unit each at the price shown,
        graded after the game. Saved in this browser only.
      </p>
      {bets.length === 0 ? (
        <p className="bets-note">No bets yet. Tap a price on the <Link className="accent-link" to="/bets">Bets tab</Link> to track it.</p>
      ) : (
        <>
          <Summary bets={bets} />
          {open.length > 0 && (
            <section className="my-bets-section">
              <h2>Open</h2>
              <ul className="my-bets-list">{open.map((b) => <BetRow key={b.id} bet={b} onRemove={remove} />)}</ul>
            </section>
          )}
          {graded.length > 0 && (
            <section className="my-bets-section">
              <h2>Graded</h2>
              <ul className="my-bets-list">{graded.map((b) => <BetRow key={b.id} bet={b} onRemove={remove} />)}</ul>
            </section>
          )}
        </>
      )}
      <p className="bets-legal">
        Closing-line value: the expected return of your price by the books&apos; last odds before puck drop, with their
        margin removed. For information and entertainment, not betting advice. 21+. If you bet, bet responsibly: gambling
        problem? Call <span className="nowrap">1-800-GAMBLER</span>.
      </p>
    </main>
  );
}
