import { useState } from "react";
import { timeAgo } from "../utils/timeAgo.js";

// A story's photo: lazy-loaded, decorative (the title says what it is),
// and gone if the image fails rather than leaving a broken box.
function Photo({ src, className }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return <img className={className} src={src} alt="" loading="lazy" onError={() => setFailed(true)} />;
}

function Meta({ story }) {
  const teams = story.teams || [];
  return (
    <span className="feed-meta">
      <span className="feed-source">{story.source}</span>
      <span>{timeAgo(story.published)}</span>
      {teams.slice(0, 3).map((t) => <span key={t} className="feed-team">{t}</span>)}
      {teams.length > 3 && <span className="feed-team">+{teams.length - 3}</span>}
    </span>
  );
}

// The News tab's headlines: the top story large with its photo and summary,
// then one card per story with a thumbnail. Every story links to the
// original (we never copy the article).
export default function NewsFeed({ headlines }) {
  if (!headlines.length) return <p className="news-empty">No headlines right now.</p>;
  const [lead, ...rest] = headlines;
  return (
    <div className="feed">
      <a className="feed-lead" href={lead.url} target="_blank" rel="noopener noreferrer">
        <Photo src={lead.image} className="feed-lead-photo" />
        <span className="feed-lead-body">
          <span className="feed-lead-title">{lead.title}</span>
          {lead.summary && <span className="feed-lead-summary">{lead.summary}</span>}
          <Meta story={lead} />
        </span>
      </a>
      <ul className="feed-list">
        {rest.map((story) => (
          <li key={story.url}>
            <a className="feed-item" href={story.url} target="_blank" rel="noopener noreferrer">
              <span className="feed-item-body">
                <span className="feed-item-title">{story.title}</span>
                <Meta story={story} />
              </span>
              <Photo src={story.thumb} className="feed-item-photo" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
