import { useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { formatPct, formatPrice } from "../utils/odds.js";

const money = (n) => `${n >= 0 ? "+" : "−"}$${Math.abs(Math.round(n))}`;
const score = (b) => (b == null ? "—" : b.toFixed(3));

function AccuracyRow({ label, beta, row }) {
  if (!row.games) return null;
  const oursBetter = row.brier_ours < row.brier_books;
  return (
    <tr>
      <th scope="row">{label}{beta && <span className="bets-exp">beta</span>}</th>
      <td className={oursBetter ? "rc-better" : undefined}>{score(row.brier_ours)}</td>
      <td className={!oursBetter ? "rc-better" : undefined}>{score(row.brier_books)}</td>
      <td className="muted">{row.games}</td>
    </tr>
  );
}

function Disagreement({ d }) {
  const leanHome = d.ours > d.books;
  const team = leanHome ? d.home : d.away;
  const ours = leanHome ? d.ours : 1 - d.ours;
  const books = leanHome ? d.books : 1 - d.books;
  const right = leanHome === d.home_won;
  return (
    <li>
      <span><strong>{d.away} @ {d.home}</strong> <span className="muted">{d.date.slice(5)}</span></span>
      <span>{team}: us {formatPct(ours)} · books {formatPct(books)}</span>
      <span className={right ? "rc-right" : "rc-wrong"}>{right ? "We were closer" : "Books were closer"}</span>
    </li>
  );
}

export default function ReportCardPage() {
  const { data, status } = useFetchWithStatus(`${API_BASE}/report-card`);
  const [period, setPeriod] = useState("week");
  const r = data?.[period];

  return (
    <main className="page report-card-page">
      <div className="page-header"><h1>Report card</h1></div>
      <p className="page-subtitle">
        How PuckPulse&apos;s predictions have done against the sportsbooks, graded on finished games. Wins and losses.
      </p>
      <div className="preview-lines-toggle" role="group" aria-label="Period">
        {[["week", "Last 7 days"], ["season", "Season"]].map(([key, label]) => (
          <button key={key} type="button" aria-pressed={period === key} onClick={() => setPeriod(key)}>{label}</button>
        ))}
      </div>

      {status === "error" ? (
        <p className="bets-note">Couldn&apos;t load the report card.</p>
      ) : !r ? (
        <p className="bets-note">Loading…</p>
      ) : r.moneyline.games === 0 ? (
        <p className="bets-note">No graded games with sportsbook odds yet.</p>
      ) : (
        <>
          <section className="pickem-card rc-tiles" aria-label="Picking winners">
            <h2>Picking winners</h2>
            <div className="rc-tile-row">
              <div className="rc-tile"><strong>{formatPct(r.moneyline.favorite_won_ours)}</strong><span>PuckPulse&apos;s favorite won</span></div>
              <div className="rc-tile"><strong>{formatPct(r.moneyline.favorite_won_books)}</strong><span>The books&apos; favorite won</span></div>
            </div>
            <p className="pickem-hint">On the {r.moneyline.games} games with sportsbook odds.</p>
          </section>

          <section className="pickem-card">
            <h2>Accuracy vs. the books</h2>
            <table className="rc-table">
              <thead><tr><th scope="col">Bet</th><th scope="col">PuckPulse</th><th scope="col">Books</th><th scope="col">Games</th></tr></thead>
              <tbody>
                <AccuracyRow label="Moneyline" row={r.moneyline} />
                <AccuracyRow label="Puck line" row={r.puck_line} />
                <AccuracyRow label="Total" beta row={r.total} />
              </tbody>
            </table>
            <p className="pickem-hint">Brier score: lower is better, and 0.250 is a coin flip. The better side is highlighted.</p>
          </section>

          <section className="pickem-card">
            <h2>Value badges</h2>
            {r.value_bets.bets === 0 ? (
              <p className="pickem-hint">
                No value badges in this stretch. That&apos;s by design: a badge needs our model to disagree with the books
                and a price paying enough to beat our fair odds.
              </p>
            ) : (
              <>
                <p className="rc-record">
                  <strong>{r.value_bets.wins}-{r.value_bets.losses}{r.value_bets.pushes ? `-${r.value_bets.pushes}` : ""}</strong>
                  {" · "}<span className={r.value_bets.profit >= 0 ? "rc-right" : "rc-wrong"}>{money(r.value_bets.profit)}</span>
                  <span className="muted"> on $100 bets</span>
                </p>
                <ul className="rc-list">
                  {r.value_bets.list.map((v) => (
                    <li key={`${v.date}-${v.game}-${v.bet}`}>
                      <span><strong>{v.bet}</strong> {formatPrice(v.price)} <span className="muted">{v.game} · {v.date.slice(5)}</span></span>
                      <span className={v.result > 0 ? "rc-right" : v.result < 0 ? "rc-wrong" : "muted"}>
                        {v.result > 0 ? `Won ${money(v.profit)}` : v.result < 0 ? "Lost $100" : "Push"}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="pickem-hint">Graded with today&apos;s badge rules on each game&apos;s last line before puck drop.</p>
              </>
            )}
          </section>

          {r.disagreements.length > 0 && (
            <section className="pickem-card">
              <h2>Where we disagreed most</h2>
              <ul className="rc-list">{r.disagreements.map((d) => <Disagreement key={`${d.date}-${d.home}`} d={d} />)}</ul>
            </section>
          )}
        </>
      )}

      <section className="bets-about">
        <h2>How to read this</h2>
        <ul>
          <li><strong>The books</strong>: the consensus of US sportsbooks with their margin removed, at the closing line when we have it (the toughest benchmark: it has the most information in it).</li>
          <li><strong>It takes a while</strong>: single hockey games are close to coin flips, so a gap smaller than about 0.01 doesn&apos;t mean much until a few hundred games are in.</li>
          <li>Every prediction is logged before puck drop and never changed. For how often our odds come true, see the <Link className="accent-link" to="/track-record">model&apos;s track record</Link>; for tonight&apos;s lines, <Link className="accent-link" to="/bets">Bets</Link>.</li>
        </ul>
        <p className="bets-legal">For information and entertainment, not betting advice. 21+. Gambling problem? Call <span className="nowrap">1-800-GAMBLER</span>.</p>
      </section>
    </main>
  );
}
