import { shortDateLabel } from "../utils/dates.js";

const STATUS_TONE = { "injured reserve": "ir", out: "out", "day-to-day": "dtd" };

function InjuryList({ injuries }) {
  if (!injuries.length) return <p className="news-empty">No reported injuries.</p>;
  return (
    <ul className="injury-list">
      {injuries.map((i) => (
        <li key={`${i.player}-${i.status}`} className="injury">
          <div className="injury-head">
            <span className="injury-player">{i.player}</span>
            {i.position && <span className="injury-pos">{i.position}</span>}
            <span className={`injury-status injury-status-${STATUS_TONE[(i.status || "").toLowerCase()] || "other"}`}>{i.status}</span>
          </div>
          <div className="injury-detail">
            {[i.injury, i.expected_return && `expected back ${shortDateLabel(i.expected_return)}`].filter(Boolean).join(" · ")}
          </div>
          {i.note && <p className="injury-note">{i.note}</p>}
        </li>
      ))}
    </ul>
  );
}

export default InjuryList;
