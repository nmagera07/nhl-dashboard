import { timeAgo } from "../utils/timeAgo.js";

// Headlines that link to the original story (we never copy the article).
function HeadlineList({ headlines, showSummary = false }) {
  if (!headlines.length) return <p className="news-empty">No headlines right now.</p>;
  return (
    <ul className="headline-list">
      {headlines.map((h) => (
        <li key={h.url} className="headline">
          <a className="headline-link" href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a>
          {showSummary && h.summary && <p className="headline-summary">{h.summary}</p>}
          <span className="headline-meta">
            {h.source} · {timeAgo(h.published)}
            {h.teams?.length > 0 && <> · {h.teams.join(", ")}</>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default HeadlineList;
