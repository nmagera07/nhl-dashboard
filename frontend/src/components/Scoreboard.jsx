import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { API_BASE } from "../config.js";
import { phase, sortGames, statusLabel } from "./gameStatus.js";
import { teamLogo } from "../utils/teamLogo.js";
import { todayISO } from "../utils/dates.js";
import { cachedResponse, rememberResponse } from "../utils/responseCache.js";
import { nhlVideoUrl } from "../utils/highlights.js";
import { pregameChance } from "../utils/seasonSim.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import FavoriteStar from "./FavoriteStar.jsx";

const scoresUrl = (date) => `${API_BASE}/games/date/${date || todayISO()}`;
const gamesIn = (response) => (Array.isArray(response?.games) ? response.games : undefined);

function networks(game) {
  const names = (game.tvBroadcasts || []).filter((b) => b.market === "N").map((b) => b.network);
  return [...new Set(names)].slice(0, 2).join(", ");
}

// chance: PuckPulse's pregame chance for this team (upcoming games only).
function TeamLine({ team, phase: gamePhase, isWinner, isLoser, chance }) {
  const showScore = gamePhase !== "upcoming";
  return (
    <span className={`game-card-team${isWinner ? " is-winner" : ""}${isLoser ? " is-loser" : ""}`}>
      {team?.logo ? <img className="game-card-logo" src={teamLogo(team.logo)} alt="" /> : <span className="game-card-logo" />}
      <span className="game-card-abbrev">{team?.abbrev || "—"}</span>
      {gamePhase === "upcoming" && team?.record && <span className="game-card-record">{team.record}</span>}
      {showScore && <strong className="game-card-score">{team?.score ?? 0}</strong>}
      {!showScore && chance != null && <span className="game-card-chance">{Math.round(chance * 100)}%</span>}
    </span>
  );
}

function GameCard({ game, onOpen, mine, inputs }) {
  const p = phase(game);
  const away = game.awayTeam;
  const home = game.homeTeam;
  const decided = p === "final" && away?.score != null && home?.score != null && away.score !== home.score;
  const awayWon = decided && away.score > home.score;
  const tv = p === "upcoming" ? networks(game) : "";
  const recap = p === "final" ? nhlVideoUrl(game.threeMinRecap) : null;
  const chance = p === "upcoming" ? pregameChance(inputs, game.gameDate, home?.abbrev, away?.abbrev) : null;
  const odds = chance ? `, PuckPulse: ${away?.abbrev} ${Math.round((1 - chance.home) * 100)}%, ${home?.abbrev} ${Math.round(chance.home * 100)}%` : "";

  return (
    <div className="game-card-wrap">
      <button
        className={`scoreboard-game game-card-${p}${mine ? " game-card-mine" : ""}`}
        type="button"
        onClick={onOpen}
        aria-label={`${away?.abbrev} at ${home?.abbrev}, ${statusLabel(game)}${odds}`}
      >
        <span className="game-card-status">
          {p === "live" && <span className="live-dot" />}
          {statusLabel(game)}
          {tv && <span className="game-card-tv">{tv}</span>}
          {mine && <FavoriteStar />}
        </span>
        <TeamLine team={away} phase={p} isWinner={decided && awayWon} isLoser={decided && !awayWon} chance={chance && 1 - chance.home} />
        <TeamLine team={home} phase={p} isWinner={decided && !awayWon} isLoser={decided && awayWon} chance={chance?.home} />
      </button>
      {/* A sibling, not inside the button: links can't nest in buttons. */}
      {recap && (
        <a className="game-card-recap" href={recap} target="_blank" rel="noopener noreferrer"
          aria-label={`Watch the ${away?.abbrev} at ${home?.abbrev} recap on NHL.com`}>
          ▶ Recap
        </a>
      )}
    </div>
  );
}

// Your team's game goes first, then the usual order (live, upcoming, final).
// Where a game ranks among the followed teams' (main team first), or -1.
const pinRank = (game, pinTeams) => {
  const ranks = [game.awayTeam?.abbrev, game.homeTeam?.abbrev].map((t) => pinTeams.indexOf(t)).filter((i) => i >= 0);
  return ranks.length ? Math.min(...ranks) : -1;
};

function orderGames(games, pinTeams) {
  const sorted = sortGames(games);
  if (!pinTeams.length) return sorted;
  const mine = sorted.filter((g) => pinRank(g, pinTeams) >= 0).sort((a, b) => pinRank(a, pinTeams) - pinRank(b, pinTeams));
  return [...mine, ...sorted.filter((g) => pinRank(g, pinTeams) < 0)];
}

// date: "YYYY-MM-DD" for another day, or null for today (which also
// refreshes every minute; other days don't change often enough to poll).
// Today is fetched by its date, not the NHL's "score/now" feed: that feed
// keeps showing last night's games until late morning, which put
// yesterday's finals under today's date.
// pinTeams: the followed teams, main first; their games lead the list.
export default function Scoreboard({ date = null, pinTeams = [] }) {
  const navigate = useNavigate();
  const location = useLocation();
  // Coming back from a box score: show the scores we just had, then refresh.
  // The cache holds the API's response as-is ({games: [...]}), the same as
  // useFetchWithStatus, since the pick'em page fetches this URL too.
  const [games, setGames] = useState(() => gamesIn(cachedResponse(scoresUrl(date))) ?? []);
  const [status, setStatus] = useState(() => (gamesIn(cachedResponse(scoresUrl(date))) ? "ready" : "loading"));
  useEffect(() => {
    let active = true;
    // Re-read "today" on each refresh, so a page left open past midnight moves on.
    const load = () => {
      const url = scoresUrl(date);
      return fetch(url)
        .then((response) => {
          if (!response.ok) throw new Error("scoreboard unavailable");
          return response.json();
        })
        .then((data) => {
          if (!active) return;
          rememberResponse(url, data);
          setGames(gamesIn(data) ?? []);
          setStatus("ready");
        })
        .catch(() => active && setStatus("error"));
    };
    load();
    const timer = date ? null : window.setInterval(load, 60_000);
    return () => { active = false; if (timer) window.clearInterval(timer); };
  }, [date]);

  // PuckPulse's pregame chances for upcoming games: the same model inputs the
  // game page and pick'em use (small, and cached), fetched only when needed.
  const anyUpcoming = games.some((g) => phase(g) === "upcoming");
  const { data: inputs } = useFetchWithStatus(anyUpcoming ? `${API_BASE}/season-sim` : null);

  // Remember which day we came from, so the box score's back link returns there.
  const openGame = (id) => navigate(`/games/${id}`, { state: { from: `${location.pathname}${location.search}` } });

  return (
    <section className="scoreboard" aria-label="Today's NHL scoreboard">
      {status === "loading" && <p className="scoreboard-empty">Loading games…</p>}
      {status === "error" && <p className="scoreboard-empty status-error">Scores are unavailable right now.</p>}
      {status === "ready" && games.length === 0 && (
        <p className="scoreboard-empty">{date ? "No games on this day." : "No games scheduled today."}</p>
      )}
      <div className="scoreboard-games">
        {orderGames(games, pinTeams).map((game) => (
          <GameCard key={game.id} game={game} onOpen={() => openGame(game.id)} mine={pinRank(game, pinTeams) >= 0} inputs={inputs} />
        ))}
      </div>
    </section>
  );
}
