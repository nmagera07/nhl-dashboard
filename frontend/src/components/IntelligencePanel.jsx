import { useState } from "react";
import { INTELLIGENCE_BASE } from "../config.js";

export default function IntelligencePanel({ context }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const ask = async (event) => {
    event.preventDefault();
    if (!message.trim()) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${INTELLIGENCE_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim(), context }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "NHL Intelligence could not answer right now.");
      }
      if (!response.body) throw new Error("NHL Intelligence returned an empty response.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      let evidence = [];
      const consume = (chunk) => {
        buffer += decoder.decode(chunk, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        events.forEach((event) => {
          const line = event.split("\n").find((item) => item.startsWith("data: "));
          if (!line) return;
          const payload = JSON.parse(line.slice(6));
          if (payload.type === "delta") {
            answer += payload.text;
            setResult({ answer, evidence });
          } else if (payload.type === "done") {
            evidence = payload.evidence || [];
            setResult({ answer, evidence });
          } else if (payload.type === "error") {
            throw new Error(payload.message);
          }
        });
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        consume(value);
      }
      consume(new Uint8Array());
    } catch (requestError) {
      setError(requestError.message || "NHL Intelligence could not answer right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="intelligence" aria-label="NHL Intelligence">
      <button
        className="intelligence-toggle"
        type="button"
        aria-expanded={open}
        aria-controls="nhl-intelligence-panel"
        onClick={() => setOpen((value) => !value)}
      >
        ✦ Ask NHL Intelligence
      </button>
      {open && (
        <div className="intelligence-panel" id="nhl-intelligence-panel">
          <div className="intelligence-heading">
            <strong>NHL Intelligence</strong>
            <span>Grounded in the stats on this page.</span>
          </div>
          <form onSubmit={ask}>
            <textarea
              aria-label="Question for NHL Intelligence"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              maxLength="1000"
              placeholder="Ask what these stats mean…"
            />
            <button type="submit" disabled={loading || !message.trim()}>
              {loading ? "Thinking…" : "Ask"}
            </button>
          </form>
          {error && <p className="intelligence-error">{error}</p>}
          {result && (
            <div className="intelligence-answer">
              <p>{result.answer}</p>
              {result.evidence?.length > 0 && (
                <small>
                  Evidence: {result.evidence.map((item) => item.label).join(" · ")}
                </small>
              )}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
