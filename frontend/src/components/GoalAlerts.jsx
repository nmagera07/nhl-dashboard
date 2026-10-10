import { useEffect, useState } from "react";
import { currentSubscription, disableAlerts, enableAlerts, pushSupport, updateAlertTeams } from "../utils/push.js";

// "🔔 Goal alerts" for the followed team: a push notification for every
// goal in its games and the final score. Adapts to what this device can do.
function GoalAlerts({ team }) {
  const [support, setSupport] = useState(() => pushSupport());
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Is this device already subscribed? If so, keep its team current.
  useEffect(() => {
    let active = true;
    currentSubscription()
      .then((sub) => {
        if (!active) return;
        setOn(Boolean(sub));
        if (sub) updateAlertTeams([team]).catch(() => {});
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [team]);

  if (support === "unsupported") return null;
  if (support === "ios-install") {
    return <span className="alerts-hint">🔔 Add to Home Screen for goal alerts</span>;
  }
  if (support === "denied") {
    return <span className="alerts-hint" title="Allow notifications for this site in your browser or phone settings">🔕 Alerts blocked in settings</span>;
  }

  const toggle = async () => {
    setBusy(true);
    setError(null);
    try {
      if (on) {
        await disableAlerts();
        setOn(false);
      } else {
        const permission = await enableAlerts([team]);
        if (permission === "granted") setOn(true);
        else setSupport(pushSupport());
      }
    } catch (e) {
      setError(e.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className={on ? "alerts-button alerts-button-on" : "alerts-button"}
        aria-pressed={on}
        disabled={busy}
        onClick={toggle}
        title={on ? "Turn off goal and final-score notifications" : `Get a notification for every ${team} goal (and goal against) and the final score`}
      >
        {busy ? "…" : on ? "🔔 Alerts on" : "🔔 Goal alerts"}
      </button>
      {error && <span className="alerts-hint alerts-error" role="alert">{error}</span>}
    </>
  );
}

export default GoalAlerts;
