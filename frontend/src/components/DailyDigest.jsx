import { useState } from "react";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { todayISO } from "../utils/dates.js";
import ChatMarkdown from "./ChatMarkdown.jsx";
import { factsAsMarkdown } from "../utils/digest.js";

function weekdayDateLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

// The headline, for the collapsed bar: the digest's bold first line, or
// last night's first result when only the facts are available.
function headline(data) {
  const first = (data.text || "").split("\n").map((l) => l.trim()).find(Boolean);
  if (first) return first.replace(/\*\*/g, "").replace(/^#+\s*/, "");
  return data.facts?.last_night?.[0]?.line || "Last night's results and tonight's games";
}

// Open or closed, remembered per day: opening today's digest keeps it open on
// the next visit, closing it keeps it out of the way of the scores.
const openKey = (date) => `puckpulse:digest-open:${date}`;
function readOpen(date) {
  try {
    return window.localStorage.getItem(openKey(date)) === "1";
  } catch {
    return false;
  }
}

// The morning digest at the top of today's scores: last night, the playoff
// race, and tonight's game of the night. Written once a day by the daily
// job + NHL Intelligence, so every visitor reads the same one. Starts
// collapsed to a one-line headline so it doesn't push the scoreboard down.
function DailyDigest() {
  const { data, status } = useFetchWithStatus(`${API_BASE}/digest/latest`);
  const date = String(data?.digest_date || "").slice(0, 10);
  const [openFor, setOpenFor] = useState({});
  if (status !== "ready" || !date || date !== todayISO()) return null;

  const open = openFor[date] ?? readOpen(date);
  const toggle = (event) => {
    const isOpen = event.currentTarget.open;
    if (isOpen === open) return;
    setOpenFor({ [date]: isOpen });
    try {
      window.localStorage.setItem(openKey(date), isOpen ? "1" : "0");
    } catch {
      // Can't remember it; it'll just start collapsed next time.
    }
  };

  return (
    <details className="daily-digest" open={open} onToggle={toggle}>
      <summary>
        <span className="daily-digest-title">☀️ Morning digest</span>
        <span className="daily-digest-date">{weekdayDateLabel(date)}</span>
        <span className="daily-digest-teaser">{headline(data)}</span>
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
