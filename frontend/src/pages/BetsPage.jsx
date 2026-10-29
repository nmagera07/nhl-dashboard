import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { useMyBets } from "../hooks/useMyBets.js";
import ValueOfTheNight from "../components/ValueOfTheNight.jsx";
import { betId, sideLine } from "../utils/myBets.js";
import { todayISO } from "../utils/dates.js";
import { formatEv, formatPct, formatPrice, formatSpread } from "../utils/odds.js";

const NOT_STARTED = new Set(["FUT", "PRE"]);
const startTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// One side of a bet: the price to bet at, PuckPulse's fair price, and a
// value badge when the price pays more than the fair odds by enough.
// Before puck drop, tapping it tracks the bet at this price (My bets).
function Side({ label, side, showBook, open, tracked, onTrack }) {
  if (!side) return <td />;
  const title = `${label}: PuckPulse's model ${formatPct(side.model ?? side.ours)}${side.market != null ? `, books ${formatPct(side.market)}, fair ${formatPct(side.ours)}` : ""}`;
  const body = (
    <>
      <span className="bets-label">{label}</span>
      <strong className="bets-price">{formatPrice(side.price)}</strong>
      {showBook && side.book && <span className="bets-book">{side.book}</span>}
      <span className="bets-fair">PuckPulse {formatPrice(side.fair)}</span>
      {side.value && open && <span className="bets-badge">Value {formatEv(side.ev)}</span>}
      {tracked && <span className="bets-tracked">✓ Tracking</span>}
    </>
  );
  const classes = ["bets-side", side.value && open && "bets-side-value", tracked && "bets-side-tracked"].filter(Boolean).join(" ");
  return (
    <td className={classes} title={title}>
      {open && onTrack && side.price != null ? (
        <button type="button" className="bets-track" aria-pressed={Boolean(tracked)} onClick={onTrack}
                aria-label={`${tracked ? "Stop tracking" : "Track"} ${label} at ${formatPrice(side.price)}`}>{body}</button>
      ) : body}
    </td>
  );
}

const lastName = (name) => name.split(" ").slice(1).join(" ") || name;

// A team's starter by the best word so far: a beat reporter's (via
// RotoWire: "confirmed" or "expected"), then NHL.com's projected lineup,
// then our projection with its chance. {name, note} or null.
function starter(board, side) {
  const reported = board.reported_starters?.[side];
  if (reported) return { name: lastName(reported.name), note: reported.status };
  const nhl = board.nhl_starters?.[side];
  if (nhl) return { name: lastName(nhl), note: "NHL.com" };
  const top = board.goalies?.[side]?.[0];
  return top ? { name: lastName(top.name), note: formatPct(top.prob) } : null;
}

function Starter({ goalie }) {
  if (!goalie) return "?";
  return <>{goalie.name} <span className="bets-goalie-note">{goalie.note}</span></>;
}

function BetCard({ game, board, tracked, onTrack }) {
  const open = NOT_STARTED.has(game.gameState);
  const away = game.awayTeam.abbrev;
  const home = game.homeTeam.abbrev;
  const tired = [board.b2b?.away && away, board.b2b?.home && home].filter(Boolean);
  const pl = board.puck_line;
  const total = board.total;
  const hasMarket = board.moneyline.home.price != null;
  const goalies = { away: starter(board, "away"), home: starter(board, "home") };
  // The props that make a side trackable: {tracked, onTrack}.
  const track = (market, side) => {
    const id = betId(game.id, market, side);
    return {
      tracked: tracked.has(id),
      onTrack: () => onTrack({
        id, gameId: game.id, date: board.date, away, home, market, side,
        line: sideLine(board, market, side), price: board[market][side].price, placedAt: new Date().toISOString(),
      }),
    };
  };
  return (
    <li className={open ? "bets-card" : "bets-card bets-card-closed"}>
      <div className="bets-head">
        <Link to={`/games/${game.id}`} className="bets-matchup">
          {away} <span className="bets-at">@</span> {home}
        </Link>
        <span className="bets-time">{open ? startTime(game.startTimeUTC) : game.gameState === "LIVE" || game.gameState === "CRIT" ? "Live" : "Final"}</span>
      </div>
      {tired.length > 0 && <p className="bets-chip">{tired.join(" & ")} on the 2nd night of a back-to-back</p>}
      {open && (goalies.away || goalies.home) && (
        <p className="bets-goalies">
          <span className="bets-goalies-label">In net</span>{" "}
          <Starter goalie={goalies.away} /> · <Starter goalie={goalies.home} />
        </p>
      )}
      {!hasMarket ? (
        <p className="bets-note">No lines yet. PuckPulse: {home} {formatPct(board.moneyline.home.ours)} ({formatPrice(board.moneyline.home.fair)}).</p>
      ) : (
        <table className="bets-table">
          <tbody>
            <tr>
              <th scope="row">Moneyline<span className="bets-row-hint">to win</span></th>
              <Side label={away} side={board.moneyline.away} showBook open={open} {...track("moneyline", "away")} />
              <Side label={home} side={board.moneyline.home} showBook open={open} {...track("moneyline", "home")} />
            </tr>
            {pl && pl.home.price != null && (
              <tr>
                <th scope="row">Puck line<span className="bets-row-hint">−1.5: win by 2+</span></th>
                <Side label={`${away} ${formatSpread(-pl.home_spread)}`} side={pl.away} open={open} {...track("puck_line", "away")} />
                <Side label={`${home} ${formatSpread(pl.home_spread)}`} side={pl.home} open={open} {...track("puck_line", "home")} />
              </tr>
            )}
            {total && total.over.price != null && (
              <tr>
                <th scope="row">Total<span className="bets-row-hint">both teams&apos; goals</span><span className="bets-exp">beta</span></th>
                <Side label={`Over ${total.line}`} side={total.over} open={open} {...track("total", "over")} />
                <Side label={`Under ${total.line}`} side={total.under} open={open} {...track("total", "under")} />
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
  const { data: value } = useFetchWithStatus(`${API_BASE}/value-of-the-night?date=${today}`);
  const myBets = useMyBets();
  const tracked = new Set(myBets.bets.map((b) => b.id));
  const boards = bets?.games || {};
  const games = (scoreboard?.games || [])
    .filter((g) => boards[String(g.id)])
    .sort((a, b) => NOT_STARTED.has(b.gameState) - NOT_STARTED.has(a.gameState) || a.startTimeUTC.localeCompare(b.startTimeUTC));
  const loading = status === "loading" || scoreStatus === "loading";

  return (
    <main className="page bets-page">
      <div className="page-header"><h1>Bets</h1></div>
      <p className="page-subtitle">
        The best price for each side, with PuckPulse&apos;s own odds under it. <strong>Value</strong> means the price
        beats ours by enough to matter. Tap a price to track it in <Link className="accent-link" to="/my-bets">My bets</Link>.{" "}
        <Link className="accent-link" to="/report-card">How we&apos;ve done vs. the books ›</Link>
      </p>
      {status === "error" ? (
        <p className="bets-note">Couldn&apos;t load today&apos;s lines.</p>
      ) : loading && games.length === 0 ? (
        <p className="bets-note">Loading…</p>
      ) : games.length === 0 ? (
        <p className="bets-note">No games today. <Link className="accent-link" to="/">See the schedule.</Link></p>
      ) : (
        <>
          <ValueOfTheNight data={value} game={games.find((g) => g.id === value?.pick?.game_id)} today={today}
                           tracked={tracked} onTrack={myBets.toggle} />
          <ul className="bets-list">
            {games.map((g) => <BetCard key={g.id} game={g} board={{ ...boards[String(g.id)], date: today }} tracked={tracked} onTrack={myBets.toggle} />)}
          </ul>
        </>
      )}
      <section className="bets-about">
        <h2>How to read this</h2>
        <ul>
          <li><strong>Price</strong>: the moneyline is the best price at a state-licensed US sportsbook (the book is named); the puck line and total are the typical price.</li>
          <li><strong>PuckPulse</strong> (under each price): the odds we think are right. For now it&apos;s 30% PuckPulse&apos;s model and 70% the books: they&apos;re sharp, and our edge on them is still being tested against the closing line. The model gets more say as it earns it.</li>
          <li><strong>Value +3%</strong>: the expected return per bet at that price, by our fair odds, shown when it&apos;s at least +2% and our model leans that way. It usually takes one book paying more than the rest. It&apos;s an estimate, not a sure thing.</li>
          <li><strong>In net</strong>: <em>confirmed</em> or <em>expected</em> is the word from beat reporters at morning skate, via{" "}
            <a className="accent-link" href="https://www.rotowire.com/hockey/" target="_blank" rel="noreferrer">RotoWire</a>. Before that, <em>NHL.com</em> is its
            projected lineup, and a percentage is our own projection from who&apos;s been starting and back-to-backs (teams usually give the
            backup the second night). In our tests the starter mattered less to who wins than rest did, so it isn&apos;t in our odds.</li>
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
