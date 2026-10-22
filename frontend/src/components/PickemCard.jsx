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

  const rankText = rank >= 0 ? `${ordinal(rank + 1)} of ${players.length}` : null;
  let headline, detail, cta;
  if (!me) {
    headline = "Can you beat PuckPulse?";
    detail = <>Pick tonight&apos;s {games.length} winners{pp?.graded ? <> · PuckPulse is {pp.correct}-{pp.graded - pp.correct}</> : null}</>;
    cta = "Play";
  } else if (open.length > 0) {
    headline = picked === games.length ? "You're all set tonight" : `${picked} of ${games.length} picked`;
    detail = rankText ? <>You&apos;re {rankText} on the leaderboard</> : <>Results post minutes after each final</>;
    cta = picked >= games.length ? "Leaderboard" : picked > 0 ? "Finish picks" : "Make picks";
  } else {
    headline = record(me.record.correct, me.record.graded);
    detail = rankText ? <>You&apos;re {rankText} on the leaderboard</> : <>Tonight&apos;s picks are locked</>;
    cta = "Leaderboard";
  }
  const leaders = players.slice(0, 3);

  return (
    <Link className="pickem-promo" to="/pickem">
      <span className="pickem-promo-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></svg>
      </span>
      <span className="pickem-promo-body">
        <span className="pickem-promo-eyebrow">Pick&apos;em</span>
        <strong className="pickem-promo-headline">{headline}</strong>
        <span className="pickem-promo-detail">{detail}</span>
        {me && open.length > 0 && (
          <span className="pickem-promo-progress" role="progressbar" aria-label="Tonight's picks"
                aria-valuemin={0} aria-valuemax={games.length} aria-valuenow={picked}>
            <span style={{ width: `${(100 * picked) / games.length}%` }} />
          </span>
        )}
        {leaders.length > 0 && (
          <span className="pickem-promo-leaders" aria-label="Leaderboard top three">
            {leaders.map((p, i) => (
              <span key={p.name} className="pickem-promo-leader">
                <span className={`pickem-medal pickem-medal-${i + 1}`}>{i + 1}</span>{p.name} <b>{p.correct}</b>
              </span>
            ))}
          </span>
        )}
      </span>
      <span className="pickem-promo-cta">{cta} ›</span>
    </Link>
  );
}
