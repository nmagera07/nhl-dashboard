import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE } from "../config.js";
import { track } from "../utils/analytics.js";

const PLACEHOLDERS = {
  idea: "What would you like to see on PuckPulse?",
  bug: "What went wrong, and on which page?",
};

// "Suggest a feature or report a bug": a small dialog that posts to the
// API's /feedback (stored for Nate; never shown publicly). Rendered into
// <body>, so it covers the phone tab bar and Ask button (the footer sits in
// the page layout's own stacking context).
export default function FeedbackForm({ onClose }) {
  const [kind, setKind] = useState("idea");
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [website, setWebsite] = useState(""); // honeypot: hidden from people
  const [state, setState] = useState("editing"); // editing | sending | sent
  const [error, setError] = useState(null);
  const messageRef = useRef(null);

  useEffect(() => {
    messageRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const send = async (e) => {
    e.preventDefault();
    setState("sending");
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, message, contact: contact || null, page: window.location.pathname, website: website || null }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(response.status === 429 ? "That's a lot of feedback! Try again in a bit." : body.detail || "Couldn't send that. Try again?");
      }
      track("feedback", { kind });
      setState("sent");
    } catch (err) {
      setError(typeof err.message === "string" ? err.message : "Couldn't send that. Try again?");
      setState("editing");
    }
  };

  return createPortal(
    <div className="feedback-backdrop" onClick={onClose}>
      <section className="feedback-dialog" role="dialog" aria-modal="true" aria-label="Send feedback" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="feedback-close" aria-label="Close" onClick={onClose}>✕</button>
        {state === "sent" ? (
          <div className="feedback-sent">
            <h2>Thanks!</h2>
            <p>I read every one of these. — Nate</p>
            <button type="button" className="feedback-send" onClick={onClose}>Done</button>
          </div>
        ) : (
          <form onSubmit={send}>
            <h2>Help make PuckPulse better</h2>
            <div className="feedback-kinds" role="group" aria-label="Type">
              {[["idea", "Suggest a feature"], ["bug", "Report a bug"]].map(([key, label]) => (
                <button key={key} type="button" aria-pressed={kind === key}
                        className={kind === key ? "feedback-kind feedback-kind-active" : "feedback-kind"} onClick={() => setKind(key)}>
                  {label}
                </button>
              ))}
            </div>
            <label className="feedback-label" htmlFor="feedback-message">Your {kind === "bug" ? "bug report" : "idea"}</label>
            <textarea id="feedback-message" ref={messageRef} value={message} onChange={(e) => setMessage(e.target.value)}
                      placeholder={PLACEHOLDERS[kind]} rows={5} maxLength={1000} required />
            <label className="feedback-label" htmlFor="feedback-contact">How to reach you <span>(optional, if you'd like a reply)</span></label>
            <input id="feedback-contact" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={120}
                   placeholder="Email or X handle" autoComplete="email" />
            <input className="feedback-honeypot" name="website" value={website} onChange={(e) => setWebsite(e.target.value)}
                   tabIndex={-1} autoComplete="off" aria-hidden="true" />
            {error && <p className="feedback-error" role="alert">{error}</p>}
            <button type="submit" className="feedback-send" disabled={state === "sending" || message.trim().length < 3}>
              {state === "sending" ? "Sending…" : "Send"}
            </button>
          </form>
        )}
      </section>
    </div>,
    document.body,
  );
}
