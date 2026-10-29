import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";

// The brief agent writes 3 Markdown bullets; show them as plain text (no Markdown or HTML rendering).
const bullets = (text) =>
  text.split("\n").map((l) => l.trim().replace(/^[-*]\s+/, "").replace(/\*\*/g, "")).filter(Boolean);

const writtenTime = (iso) =>
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// What matters tonight, researched by PuckPulse AI before puck drop. Collapsed by
// default, and hidden until a brief has been written (late morning on game day).
function PregameBrief({ gameId }) {
  const { data } = useFetchWithStatus(`${API_BASE}/games/${gameId}/brief`);
  if (!data?.available) return null;
  return (
    <section className="boxscore-card">
      <details className="preview-lines pregame-brief">
        <summary>
          <h2>Pregame brief</h2>
          <span className="muted">What matters tonight · updated {writtenTime(data.written_at)}</span>
        </summary>
        <ul>
          {bullets(data.text).map((b) => <li key={b}>{b}</li>)}
        </ul>
        <p className="preview-note">
          Researched and written by PuckPulse AI{data.model ? ` (${data.model})` : ""} from PuckPulse&apos;s data; every
          number is checked against it. Starters and lines can change until puck drop. For entertainment, not betting
          advice. 21+. If you bet, bet responsibly: <span className="nowrap">1-800-GAMBLER</span>.
        </p>
      </details>
    </section>
  );
}

export default PregameBrief;
