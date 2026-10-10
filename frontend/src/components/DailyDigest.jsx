import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { todayISO } from "../utils/dates.js";
import ChatMarkdown from "./ChatMarkdown.jsx";
import { factsAsMarkdown } from "../utils/digest.js";

function shortDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

// The morning digest at the top of today's scores: last night, the playoff
// race, and tonight's game of the night. Written once a day by the daily
// job + NHL Intelligence, so every visitor reads the same one.
function DailyDigest() {
  const { data, status } = useFetchWithStatus(`${API_BASE}/digest/latest`);
  if (status !== "ready" || !data?.digest_date || String(data.digest_date).slice(0, 10) !== todayISO()) return null;

  return (
    <details className="daily-digest" open>
      <summary>
        <span className="daily-digest-title">☀️ Morning digest</span>
        <span className="daily-digest-date">{shortDate(String(data.digest_date).slice(0, 10))}</span>
      </summary>
      <div className="daily-digest-body">
        <ChatMarkdown text={data.text || factsAsMarkdown(data.facts || {})} />
      </div>
      <p className="daily-digest-meta">
        {data.text
          ? `Written by ${data.model || "AI"} from last night's results and the playoff-odds model.`
          : "Today's highlights, straight from the data."}
      </p>
    </details>
  );
}

export default DailyDigest;
