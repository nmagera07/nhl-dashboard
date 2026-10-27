import { useEffect, useState } from "react";
import { alertPrefs, currentSubscription, disableAlerts, enableAlerts, pushSupport, setAlertPrefs, updateAlertTeams } from "../utils/push.js";

const KINDS = [
  ["starts", "Puck drop"],
  ["goals", "Goals by my teams"],
  ["goals_against", "Goals against"],
  ["finals", "Final scores"],
];

// What this device is alerted about, and for which followed teams. Each
// change re-saves the subscription, so the notifier filters before sending.
function AlertSettings({ teams, onClose }) {
  const [prefs, setPrefs] = useState(alertPrefs);
  const [error, setError] = useState(null);
  const change = (next) => {
    setPrefs(next);
    setAlertPrefs(next);
    setError(null);
    updateAlertTeams(teams).catch(() => setError("Couldn't save that. Check your connection and try again."));
  };
  const alerted = teams.filter((t) => !prefs.muted.includes(t));

  return (
    <fieldset className="alert-settings">
      <legend>Alert me about</legend>
      {KINDS.map(([key, label]) => (
        <label key={key}>
          <input type="checkbox" checked={prefs[key]} onChange={(e) => change({ ...prefs, [key]: e.target.checked })} /> {label}
        </label>
      ))}
      {teams.length > 1 && (
        <div className="alert-settings-teams" role="group" aria-label="Teams">
          <span>For</span>
          {teams.map((t) => {
            const on = !prefs.muted.includes(t);
            return (
              <label key={t}>
                <input type="checkbox" checked={on} disabled={on && alerted.length === 1}
                       onChange={(e) => change({ ...prefs, muted: e.target.checked ? prefs.muted.filter((m) => m !== t) : [...prefs.muted, t] })} /> {t}
              </label>
            );
          })}
        </div>
      )}
      {error && <p className="alerts-hint alerts-error" role="alert">{error}</p>}
      <button type="button" className="link-button" onClick={onClose}>Done</button>
    </fieldset>
  );
}

// "🔔 Goal alerts" for the followed teams: a push notification at puck
// drop, for every goal in their games, and the final score. Adapts to what
// this device can do.
function GoalAlerts({ teams }) {
  const key = teams.join(",");
  const [support, setSupport] = useState(() => pushSupport());
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Is this device already subscribed? If so, keep its team current.
  useEffect(() => {
    let active = true;
    currentSubscription()
      .then((sub) => {
        if (!active) return;
        setOn(Boolean(sub));
        if (sub) updateAlertTeams(key.split(",")).catch(() => {});
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [key]);

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
        setSettingsOpen(false);
      } else {
        const permission = await enableAlerts(teams);
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
        title={on ? "Turn off game notifications" : `Get a notification at puck drop, for every ${teams.join(", ")} goal (and goal against), and the final score`}
      >
        {busy ? "…" : on ? "🔔 Alerts on" : "🔔 Goal alerts"}
      </button>
      {on && !settingsOpen && (
        <button type="button" className="link-button alerts-settings-link" onClick={() => setSettingsOpen(true)}>Alert settings</button>
      )}
      {on && settingsOpen && <AlertSettings teams={teams} onClose={() => setSettingsOpen(false)} />}
      {error && <span className="alerts-hint alerts-error" role="alert">{error}</span>}
    </>
  );
}

export default GoalAlerts;
