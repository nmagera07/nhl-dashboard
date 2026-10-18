import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { todayISO } from "../utils/dates.js";
import { formatEv, formatPct, formatPrice, formatSpread } from "../utils/odds.js";

const NOT_STARTED = new Set(["FUT", "PRE"]);
const startTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// One side of a bet: the price to bet at, PuckPulse's fair price, and a
// value badge when the price pays more than the fair odds by enough.
function Side({ label, side, showBook, open }) {
  if (!side) return <td />;
  const title = `${label}: PuckPulse's model ${formatPct(side.model ?? side.ours)}${side.market != null ? `, books ${formatPct(side.market)}, fair ${formatPct(side.ours)}` : ""}`;
  return (
    <td className={side.value && open ? "bets-side bets-side-value" : "bets-side"} title={title}>
      <span className="bets-label">{label}</span>
      <strong className="bets-price">{formatPrice(side.price)}</strong>
      {showBook && side.book && <span className="bets-book">{side.book}</span>}
      <span className="bets-fair">fair {formatPrice(side.fair)}</span>
      {side.value && open && <span className="bets-badge">Value {formatEv(side.ev)}</span>}
    </td>
  );
}

const lastName = (name) => name.split(" ").slice(1).join(" ") || name;

// "Silovs 62%": a team's likeliest starter by our projection, by last name.
function goalieLabel(goalies) {
  const top = goalies?.[0];
  return top ? `${lastName(top.name)} ${formatPct(top.prob)}` : null;
}

function BetCard({ game, board }) {
  const open = NOT_STARTED.has(game.gameState);
  const away = game.awayTeam.abbrev;
  const home = game.homeTeam.abbrev;
  const tired = [board.b2b?.away && away, board.b2b?.home && home].filter(Boolean);
  const pl = board.puck_line;
  const total = board.total;
  const hasMarket = board.moneyline.home.price != null;
  return (
    <li className={open ? "bets-card" : "bets-card bets-card-closed"}>
      <div className="bets-head">
        <Link to={`/games/${game.id}`} className="bets-matchup">
          {away} <span className="bets-at">@</span> {home}
        </Link>
        <span className="bets-time">{open ? startTime(game.startTimeUTC) : game.gameState === "LIVE" || game.gameState === "CRIT" ? "Live" : "Final"}</span>
      </div>
      {tired.length > 0 && <p className="bets-chip">{tired.join(" & ")} on the 2nd night of a back-to-back</p>}
      {open && board.nhl_starters?.away && board.nhl_starters?.home ? (
        <p className="bets-goalies">
          <span className="bets-goalies-label">In net (NHL.com projects)</span>{" "}
          {lastName(board.nhl_starters.away)} · {lastName(board.nhl_starters.home)}
        </p>
      ) : open && (goalieLabel(board.goalies?.away) || goalieLabel(board.goalies?.home)) ? (
        <p className="bets-goalies">
          <span className="bets-goalies-label">In net (projected)</span>{" "}
          {goalieLabel(board.goalies?.away) || "?"} · {goalieLabel(board.goalies?.home) || "?"}
        </p>
      ) : null}
      {!hasMarket ? (
        <p className="bets-note">No lines yet. PuckPulse: {home} {formatPct(board.moneyline.home.ours)} (fair {formatPrice(board.moneyline.home.fair)}).</p>
      ) : (
        <table className="bets-table">
          <tbody>
            <tr>
              <th scope="row">Moneyline</th>
              <Side label={away} side={board.moneyline.away} showBook open={open} />
              <Side label={home} side={board.moneyline.home} showBook open={open} />
            </tr>
            {pl && pl.home.price != null && (
              <tr>
                <th scope="row">Puck line</th>
                <Side label={`${away} ${formatSpread(-pl.home_spread)}`} side={pl.away} open={open} />
                <Side label={`${home} ${formatSpread(pl.home_spread)}`} side={pl.home} open={open} />
              </tr>
            )}
            {total && total.over.price != null && (
              <tr>
                <th scope="row">Total <span className="bets-exp">beta</span></th>
                <Side label={`Over ${total.line}`} side={total.over} open={open} />
                <Side label={`Under ${total.line}`} side={total.under} open={open} />
              </tr>
            )}
          </tbody>
        </table>
      )}
      {!open && <p className="bets-note">Started: these were the last lines before puck drop.</p>}
    </li>
  );
}

export default function BetsPage() {
  const today = todayISO();
  const { data: scoreboard, status: scoreStatus } = useFetchWithStatus(`${API_BASE}/games/date/${today}`);
  const { data: bets, status } = useFetchWithStatus(`${API_BASE}/bets?date=${today}`);
  const boards = bets?.games || {};
  const games = (scoreboard?.games || [])
    .filter((g) => boards[String(g.id)])
    .sort((a, b) => NOT_STARTED.has(b.gameState) - NOT_STARTED.has(a.gameState) || a.startTimeUTC.localeCompare(b.startTimeUTC));
  const loading = status === "loading" || scoreStatus === "loading";

  return (
    <main className="page bets-page">
      <div className="page-header"><h1>Bets</h1></div>
      <p className="page-subtitle">
        Today&apos;s lines next to PuckPulse&apos;s fair odds. <strong>Value</strong> means a price that returns at
        least 2% by our fair odds.
      </p>
      {status === "error" ? (
        <p className="bets-note">Couldn&apos;t load today&apos;s lines.</p>
      ) : loading && games.length === 0 ? (
        <p className="bets-note">Loading…</p>
      ) : games.length === 0 ? (
        <p className="bets-note">No games today. <Link className="accent-link" to="/">See the schedule.</Link></p>
      ) : (
        <ul className="bets-list">
          {games.map((g) => <BetCard key={g.id} game={g} board={boards[String(g.id)]} />)}
        </ul>
      )}
      <section className="bets-about">
        <h2>How to read this</h2>
        <ul>
          <li><strong>Price</strong>: the moneyline is the best price at a state-licensed US sportsbook (the book is named); the puck line and total are the typical price.</li>
          <li><strong>Fair</strong>: the price we think is right. For now it&apos;s 30% PuckPulse&apos;s model and 70% the books: they&apos;re sharp, and our edge on them is still being tested against the closing line. The model gets more say as it earns it.</li>
          <li><strong>Value +3%</strong>: the expected return per bet at that price, by our fair odds, shown when it&apos;s at least +2% and our model leans that way. It usually takes one book paying more than the rest. It&apos;s an estimate, not a sure thing.</li>
          <li><strong>In net</strong>: NHL.com&apos;s projected starters once its lineups are posted (a few hours before puck drop); before that, our projection, with each goalie&apos;s chance, from who&apos;s been starting and back-to-backs (teams usually give the backup the second night). Teams confirm at puck drop. In our tests the starter mattered less to who wins than rest did, so it isn&apos;t in our odds.</li>
          <li><strong>Totals (beta)</strong>: in testing, our totals didn&apos;t beat a league-average guess, so they never get a value badge.</li>
        </ul>
        <p className="bets-legal">
          Odds via The Odds API, refreshed each morning and about 15 minutes before puck drop. For information and
          entertainment, not betting advice. 21+. If you bet, bet responsibly: gambling problem? Call{" "}
          <span className="nowrap">1-800-GAMBLER</span>.
        </p>
      </section>
    </main>
  );
}
