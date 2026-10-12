import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { useFavoriteTeam } from "../hooks/useFavoriteTeam.js";
import HeadlineList from "../components/HeadlineList.jsx";
import DailyDigest from "../components/DailyDigest.jsx";
import InjuryList from "../components/InjuryList.jsx";

const VIEWS = ["Headlines", "Injuries", "Transactions"];

function Status({ status, what, children }) {
  if (status === "error") return <p className="status-line status-error">Couldn't load {what}.</p>;
  if (status === "loading" || status === "idle") return <p className="status-line">Loading {what}…</p>;
  return children;
}

// The News tab: headlines from NHL.com, ESPN, and Sportsnet (linking out),
// injuries by team, and recent transactions. Your team comes first.
function NewsPage({ standings }) {
  const [view, setView] = useState("Headlines");
  const [favorite] = useFavoriteTeam();
  const [mineOnly, setMineOnly] = useState(false);

  const newsUrl = `${API_BASE}/news?limit=40${mineOnly && favorite ? `&team=${favorite}` : ""}`;
  const { data: news, status: newsStatus } = useFetchWithStatus(newsUrl, { initialData: { headlines: [], sources: [] } });
  const { data: injuries, status: injuryStatus } = useFetchWithStatus(
    view === "Injuries" ? `${API_BASE}/injuries` : null, { initialData: { teams: {} } });
  const { data: moves, status: moveStatus } = useFetchWithStatus(
    view === "Transactions" ? `${API_BASE}/transactions?limit=40` : null, { initialData: { transactions: [] } });

  const names = useMemo(() => Object.fromEntries(standings.map((r) => [r.team_abbrev, r.team_name])), [standings]);
  const injuredTeams = useMemo(() => {
    const teams = Object.keys(injuries.teams || {}).filter((t) => injuries.teams[t].length);
    return teams.sort((a, b) => (a === favorite ? -1 : b === favorite ? 1 : (names[a] || a).localeCompare(names[b] || b)));
  }, [injuries, favorite, names]);

  return (
    <main className="page news-page">
      <div className="page-header">
        <h1>News</h1>
      </div>
      <div className="news-controls">
        <div className="view-toggle" role="group" aria-label="News view">
          {VIEWS.map((v) => (
            <button key={v} type="button" aria-pressed={v === view} onClick={() => setView(v)}
              className={v === view ? "view-toggle-btn view-toggle-btn-active" : "view-toggle-btn"}>{v}</button>
          ))}
        </div>
        {view === "Headlines" && favorite && (
          <label className="news-mine">
            <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> Only {favorite}
          </label>
        )}
      </div>

      {/* The morning digest: our own take on last night, tied to the model's odds. */}
      {view === "Headlines" && <DailyDigest />}

      {view === "Headlines" && (
        <section className="news-card" aria-label="Headlines">
          <Status status={newsStatus} what="headlines">
            <HeadlineList headlines={news.headlines || []} showSummary />
            {news.sources?.length > 0 && <p className="data-credit">From {news.sources.join(", ")}. Stories open on their site.</p>}
          </Status>
        </section>
      )}

      {view === "Injuries" && (
        <Status status={injuryStatus} what="injuries">
          {/* One collapsed row per team (30 teams' lists is a long scroll); yours starts open. */}
          <div className="news-card injury-teams">
            {injuredTeams.map((t) => (
              <details key={t} className="injury-team" open={t === favorite}>
                <summary>
                  <span className="injury-team-name">{names[t] || t}{t === favorite && " ★"}</span>
                  <span className="injury-team-count">{injuries.teams[t].length}</span>
                </summary>
                <InjuryList injuries={injuries.teams[t]} />
                <Link className="accent-link injury-team-link" to={`/teams/${t}`}>Team page ›</Link>
              </details>
            ))}
          </div>
          <p className="data-credit">Injury reports from ESPN.</p>
        </Status>
      )}

      {view === "Transactions" && (
        <section className="news-card" aria-label="Transactions">
          <Status status={moveStatus} what="transactions">
            <ul className="transaction-list">
              {(moves.transactions || []).map((m, i) => (
                <li key={`${m.date}-${m.team}-${i}`} className="transaction">
                  <span className="transaction-meta">{m.date.slice(5).replace("-", "/")} · <Link to={`/teams/${m.team}`}>{m.team}</Link></span>
                  <span>{m.description}</span>
                </li>
              ))}
            </ul>
            <p className="data-credit">Transactions from ESPN.</p>
          </Status>
        </section>
      )}
    </main>
  );
}

export default NewsPage;
