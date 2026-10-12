import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import HeadlineList from "./HeadlineList.jsx";

// The Scores page's three freshest headlines. Quietly absent if news is down.
function TopHeadlines() {
  const { data, status } = useFetchWithStatus(`${API_BASE}/news?limit=3`, { initialData: { headlines: [] } });
  if (status !== "ready" || !data.headlines?.length) return null;
  return (
    <section className="news-card top-headlines" aria-labelledby="top-headlines-title">
      <div className="news-card-header">
        <h2 id="top-headlines-title" className="news-card-title">Headlines</h2>
        <Link className="accent-link" to="/news">More news ›</Link>
      </div>
      <HeadlineList headlines={data.headlines} />
    </section>
  );
}

export default TopHeadlines;
