import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import HeadlineList from "./HeadlineList.jsx";
import InjuryList from "./InjuryList.jsx";

// A team page's news: its latest headlines and its injury report.
function TeamNews({ abbrev }) {
  const { data: news, status: newsStatus } = useFetchWithStatus(`${API_BASE}/news?team=${abbrev}&limit=4`, { initialData: { headlines: [] } });
  const { data: inj, status: injStatus } = useFetchWithStatus(`${API_BASE}/injuries?team=${abbrev}`, { initialData: { teams: {} } });
  const injuries = inj.teams?.[abbrev] || [];
  const headlines = news.headlines || [];
  if (newsStatus !== "ready" && injStatus !== "ready") return null;
  if (!headlines.length && !injuries.length) return null;
  return (
    <div className="team-news">
      {headlines.length > 0 && (
        <section className="news-card" aria-labelledby="team-headlines">
          <div className="news-card-header">
            <h2 id="team-headlines" className="news-card-title">Latest news</h2>
            <Link className="accent-link" to="/news">All news ›</Link>
          </div>
          <HeadlineList headlines={headlines} />
        </section>
      )}
      {injStatus === "ready" && (
        <section className="news-card" aria-labelledby="team-injuries">
          <h2 id="team-injuries" className="news-card-title">Injuries</h2>
          <InjuryList injuries={injuries} />
        </section>
      )}
    </div>
  );
}

export default TeamNews;
