import { useEffect, useRef, useState } from "react";
import { INTELLIGENCE_BASE } from "../config.js";
import ChatMarkdown from "./ChatMarkdown.jsx";
import { SUGGESTIONS } from "./chatSuggestions.js";

// Follow-ups: send the last 2 exchanges so "what about their power play?"
// makes sense. The service enforces the same cap.
const HISTORY_MESSAGES = 4;
const FALLBACK_ERROR = "NHL Intelligence could not answer right now.";

let nextId = 0;
const newId = () => ++nextId;

async function streamAnswer({ message, context, history, onDelta, onDone }) {
  const response = await fetch(`${INTELLIGENCE_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context, history }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || FALLBACK_ERROR);
  }
  if (!response.body) throw new Error("NHL Intelligence returned an empty response.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const consume = (chunk) => {
    buffer += decoder.decode(chunk, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    events.forEach((event) => {
      const line = event.split("\n").find((item) => item.startsWith("data: "));
      if (!line) return;
      const payload = JSON.parse(line.slice(6));
      if (payload.type === "delta") onDelta(payload.text);
      else if (payload.type === "done") onDone(payload);
      else if (payload.type === "error") throw new Error(payload.message);
    });
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    consume(value);
  }
  consume(new Uint8Array());
}

export default function IntelligencePanel({ context, label }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]); // {id, role, content, model, evidence, error, pending}
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const threadRef = useRef(null);

  // A new page means new data: start a fresh conversation.
  const contextKey = JSON.stringify(context);
  const [threadKey, setThreadKey] = useState(contextKey);
  if (threadKey !== contextKey) {
    setThreadKey(contextKey);
    setMessages([]);
  }

  useEffect(() => {
    if (!open) return undefined;
    inputRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [messages]);

  const updateLast = (patch) =>
    setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 ? { ...m, ...patch(m) } : m)));

  const send = async (text) => {
    const question = text.trim();
    if (!question || loading) return;
    const history = messages
      .filter((m) => !m.error && !m.pending && m.content)
      .slice(-HISTORY_MESSAGES)
      .map(({ role, content }) => ({ role, content }));

    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: question },
      { id: newId(), role: "assistant", content: "", pending: true },
    ]);
    try {
      await streamAnswer({
        message: question,
        context,
        history,
        onDelta: (delta) => updateLast((m) => ({ content: m.content + delta })),
        onDone: (payload) => updateLast(() => ({ pending: false, model: payload.model, evidence: payload.evidence || [] })),
      });
      updateLast(() => ({ pending: false }));
    } catch (error) {
      updateLast(() => ({ pending: false, error: error.message || FALLBACK_ERROR }));
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const suggestions = SUGGESTIONS[context.page] || SUGGESTIONS.standings;

  return (
    <aside className="intelligence" aria-label="NHL Intelligence">
      {!open && (
        <button
          className="intelligence-toggle"
          type="button"
          aria-expanded={false}
          aria-label="Ask NHL Intelligence"
          onClick={() => setOpen(true)}
        >
          <span aria-hidden="true">✦ </span>
          {/* Full label on desktop; just "Ask" on phones so it covers less content. */}
          <span className="intelligence-toggle-full" aria-hidden="true">Ask NHL Intelligence</span>
          <span className="intelligence-toggle-short" aria-hidden="true">Ask</span>
        </button>
      )}

      {open && (
        <>
          <div className="intelligence-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />
          <section className="intelligence-drawer" role="dialog" aria-label="NHL Intelligence chat">
            <header className="intelligence-header">
              <div>
                <strong>✦ NHL Intelligence</strong>
                <span className="intelligence-context">Asking about: {label}</span>
              </div>
              <div className="intelligence-header-actions">
                {messages.length > 0 && (
                  <button type="button" className="intelligence-icon-btn" onClick={() => setMessages([])} disabled={loading}>
                    New chat
                  </button>
                )}
                <button type="button" className="intelligence-icon-btn" aria-label="Close chat" onClick={() => setOpen(false)}>✕</button>
              </div>
            </header>

            <div className="intelligence-thread" ref={threadRef} aria-live="polite">
              {messages.length === 0 && (
                <div className="intelligence-empty">
                  <p>Ask anything about the stats on this page. Answers use only this page's data.</p>
                  <div className="intelligence-suggestions">
                    {suggestions.map((s) => (
                      <button key={s} type="button" className="intelligence-suggestion" onClick={() => send(s)}>{s}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="chat-msg chat-msg-user">{m.content}</div>
                ) : (
                  <div key={m.id} className="chat-msg chat-msg-ai">
                    {m.error ? (
                      <p className="intelligence-error">{m.error}</p>
                    ) : m.content ? (
                      <ChatMarkdown text={m.content} />
                    ) : (
                      <p className="intelligence-typing" aria-label="Thinking">Thinking…</p>
                    )}
                    {!m.pending && !m.error && (m.model || m.evidence?.length > 0) && (
                      <small className="intelligence-meta">
                        {m.evidence?.length > 0 && <>Evidence: {m.evidence.map((e) => e.label).join(" · ")}</>}
                        {m.model && <span className="intelligence-model">Answered by {m.model}</span>}
                      </small>
                    )}
                  </div>
                )
              )}
            </div>

            <form className="intelligence-composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
              <textarea
                ref={inputRef}
                rows={1}
                aria-label="Question for NHL Intelligence"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  // Grow with the text (Safari lacks CSS field-sizing).
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                }}
                onKeyDown={onKeyDown}
                maxLength="1000"
                placeholder={messages.length ? "Ask a follow-up…" : "Ask about this page…"}
              />
              <button type="submit" aria-label="Send" disabled={loading || !input.trim()}>
                <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h12M10 4l6 6-6 6" /></svg>
              </button>
            </form>
            <p className="intelligence-footnote">AI-generated from this page's stats. It can make mistakes.</p>
          </section>
        </>
      )}
    </aside>
  );
}
