import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { todayISO } from "../utils/dates.js";
import { fetchMe, ordinal, pickable, pickOpen, record, savedKey } from "../utils/pickem.js";

// The Scores page's way into "Beat PuckPulse": where you stand tonight (or
// PuckPulse's record, before you join) and the top of the leaderboard. Sits
// below the scoreboard; hidden on days without games.
export default function PickemCard() {
  const key = savedKey();
  const today = todayISO();
  const { data: scores } = useFetchWithStatus(`${API_BASE}/games/date/${today}`);
  const { data: board } = useFetchWithStatus(`${API_BASE}/pickem/leaderboard`);
  const [me, setMe] = useState(null);

  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    fetchMe(key, today).then((m) => !cancelled && setMe(m)).catch(() => {});
    return () => { cancelled = true; };
  }, [key, today]);

  const games = (scores?.games || []).filter(pickable);
  if (games.length === 0) return null;
  const open = games.filter((g) => pickOpen(g));
  const picked = me ? games.filter((g) => me.picks?.[String(g.id)]).length : 0;
  const players = board?.players || [];
  const rank = me ? players.findIndex((p) => p.name === me.name) : -1;
  const pp = board?.puckpulse;

  let status;
  if (!me) {
    status = <>Pick tonight&apos;s winners{pp?.graded ? <> · PuckPulse is {pp.correct}-{pp.graded - pp.correct}</> : null}</>;
  } else if (open.length > 0) {
    status = <>You&apos;ve picked {picked} of {games.length}{rank >= 0 && <> · {ordinal(rank + 1)} of {players.length}</>}</>;
  } else {
    status = <>{record(me.record.correct, me.record.graded)}{rank >= 0 && <> · {ordinal(rank + 1)} of {players.length}</>}</>;
  }
  const leaders = players.slice(0, 3);

  return (
    <Link className="pickem-link" to="/pickem">
      <span className="pickem-link-text">
        <span><strong>Beat PuckPulse</strong> · {status}</span>
        {leaders.length > 0 && (
          <span className="pickem-leaders">
            Leaders: {leaders.map((p, i) => `${i + 1}. ${p.name} (${p.correct})`).join(" · ")}
          </span>
        )}
      </span>
      <span aria-hidden="true">›</span>
    </Link>
  );
}
