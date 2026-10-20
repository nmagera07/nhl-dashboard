import { timeAgo } from "../utils/timeAgo.js";

// The News tab's Fantasy view: short player updates (RotoWire), then
// fantasy articles (DobberHockey, RotoBaller). Everything links out.
export default function FantasyFeed({ updates, articles }) {
  return (
    <>
      <section className="news-card" aria-labelledby="fantasy-updates-title">
        <h2 className="news-card-title" id="fantasy-updates-title">Player updates</h2>
        {updates.length === 0 ? (
          <p className="news-empty">No player updates right now.</p>
        ) : (
          <ul className="fantasy-updates">
            {updates.map((u) => (
              <li key={u.id}>
                <a className="fantasy-update" href={u.url} target="_blank" rel="noopener noreferrer">
                  <span className="fantasy-update-title"><strong>{u.player}</strong>: {u.title}</span>
                  {u.summary && <span className="fantasy-update-summary">{u.summary}</span>}
                  <span className="feed-meta">
                    <span className="feed-source">{u.source}</span>
                    <span>{timeAgo(u.published)}</span>
                    {u.team && <span className="feed-team">{u.team}</span>}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {articles.length > 0 && (
        <section aria-labelledby="fantasy-articles-title">
          <h2 className="news-card-title fantasy-articles-title" id="fantasy-articles-title">Fantasy articles</h2>
          <ul className="feed-list">
            {articles.map((a) => (
              <li key={a.url}>
                <a className="feed-item" href={a.url} target="_blank" rel="noopener noreferrer">
                  <span className="feed-item-body">
                    <span className="feed-item-title">{a.title}</span>
                    <span className="feed-meta">
                      <span className="feed-source">{a.source}</span>
                      <span>{timeAgo(a.published)}</span>
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
