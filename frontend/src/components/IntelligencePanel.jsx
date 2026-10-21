import { useEffect, useRef, useState } from "react";
import { useKeepAboveKeyboard } from "../hooks/useKeepAboveKeyboard.js";
import { INTELLIGENCE_BASE } from "../config.js";
import ChatMarkdown from "./ChatMarkdown.jsx";
import { suggestionsFor } from "./chatSuggestions.js";
import { warmUpChat } from "../utils/warmUp.js";
import { startChatTimer } from "../utils/chatTiming.js";
import { track } from "../utils/analytics.js";

// Follow-ups: send the last 2 exchanges so "what about their power play?"
// makes sense. The service enforces the same cap.
const HISTORY_MESSAGES = 4;
const FALLBACK_ERROR = "PuckPulse AI could not answer right now.";

const STICK_THRESHOLD_PX = 48;
// The conversation survives page changes and reloads within the tab.
const STORAGE_KEY = "pp-chat-v1";
const MAX_SAVED = 30;

function loadSaved() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter((m) => m && typeof m.content === "string") : [];
  } catch {
    return [];
  }
}

function save(messages) {
  try {
    const done = messages.filter((m) => !m.pending && !m.retryIn).slice(-MAX_SAVED);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(done.map(({ id, role, content, model, evidence, error }) => ({ id, role, content, model, evidence, error }))));
  } catch {
    // private mode or storage full: the chat still works, it just won't survive a reload
  }
}

// When every free AI provider is busy, the service says how long to wait;
// the panel counts down and tries once more on its own.
class BusyError extends Error {
  constructor(message, retryAfter) {
    super(message);
    this.retryAfter = retryAfter;
  }
}

function isTouchScreen() {
  return typeof window.matchMedia === "function" && window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}

// Unique across reloads too: restored messages keep the ids they were saved with.
let nextId = 0;
const newId = () => `${Date.now().toString(36)}-${++nextId}`;

async function streamAnswer({ message, context, history, onStatus, onDelta, onReset, onDone }) {
  const response = await fetch(`${INTELLIGENCE_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context, history }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || FALLBACK_ERROR);
  }
  if (!response.body) throw new Error("PuckPulse AI returned an empty response.");

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
      if (payload.type === "status") onStatus?.(payload.text);
      else if (payload.type === "delta") onDelta(payload.text);
      // The model wrote a little, then decided to look something up: drop that text.
      else if (payload.type === "reset") onReset?.();
      else if (payload.type === "done") onDone(payload);
      else if (payload.type === "error") throw payload.retry_after ? new BusyError(payload.message, payload.retry_after) : new Error(payload.message);
    });
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    consume(value);
  }
  consume(new Uint8Array());
}

export default function IntelligencePanel({ context, label, topic, favoriteTeamName }) {
  const [open, setOpen] = useState(false);
  // {id, role ("user" | "assistant" | "divider"), content, model, evidence, error, pending, retryIn}
  const [messages, setMessages] = useState(loadSaved);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const threadRef = useRef(null);
  const drawerRef = useRef(null);
  // Follow new text only while the reader is at the bottom. Snapping down on
  // every streamed word made it impossible to scroll up mid-answer.
  const stickToBottom = useRef(true);

  // A new page brings new data, but the conversation carries on: a marker
  // says where the next answers come from.
  const contextKey = JSON.stringify(context);
  const [threadKey, setThreadKey] = useState(contextKey);
  if (threadKey !== contextKey) {
    setThreadKey(contextKey);
    setMessages((prev) => (prev.length && prev[prev.length - 1].role !== "divider"
      ? [...prev, { id: newId(), role: "divider", content: `Now on: ${label}` }]
      : prev));
  }

  useEffect(() => save(messages), [messages]);

  useEffect(() => {
    if (!open) return undefined;
    warmUpChat();
    // Phones: don't open the keyboard until the reader taps the box; it
    // covers the suggestions and shoves the sheet up.
    if (!isTouchScreen()) inputRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread && stickToBottom.current) thread.scrollTop = thread.scrollHeight;
  }, [messages]);

  useKeepAboveKeyboard(open, drawerRef);

  const onThreadScroll = (e) => {
    const t = e.currentTarget;
    stickToBottom.current = t.scrollHeight - t.scrollTop - t.clientHeight < STICK_THRESHOLD_PX;
  };

  const updateLast = (patch) =>
    setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 ? { ...m, ...patch(m) } : m)));

  const send = async (text) => {
    const question = text.trim();
    if (!question || loading) return;
    const history = messages
      .filter((m) => (m.role === "user" || m.role === "assistant") && !m.error && !m.pending && m.content)
      .slice(-HISTORY_MESSAGES)
      .map(({ role, content }) => ({ role, content }));

    track("ai-question");
    setInput("");
    stickToBottom.current = true; // show the question just asked
    if (inputRef.current) inputRef.current.style.height = "auto";
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: question },
      { id: newId(), role: "assistant", content: "", pending: true },
    ]);
    const timer = startChatTimer();
    const ask = () => streamAnswer({
      message: question,
      context,
      history,
      onStatus: (status) => {
        timer.status();
        updateLast(() => ({ status }));
      },
      onDelta: (delta) => {
        timer.text();
        updateLast((m) => ({ content: m.content + delta }));
      },
      onReset: () => updateLast(() => ({ content: "" })),
      onDone: (payload) => updateLast(() => ({ pending: false, model: payload.model, evidence: payload.evidence || [] })),
    });
    try {
      try {
        await ask();
      } catch (error) {
        if (!(error instanceof BusyError)) throw error;
        track("ai-busy");
        for (let left = error.retryAfter; left > 0; left -= 1) {
          updateLast(() => ({ content: "", retryIn: left }));
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        updateLast(() => ({ content: "", retryIn: null, status: "Trying again…" }));
        await ask();
      }
      updateLast(() => ({ pending: false }));
      timer.finish();
    } catch (error) {
      updateLast(() => ({ pending: false, retryIn: null, error: error.message || FALLBACK_ERROR }));
      timer.finish({ error: true });
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

  const suggestions = suggestionsFor({ page: context.page, topic, team: favoriteTeamName });

  return (
    <aside className="intelligence" aria-label="PuckPulse AI">
      {!open && (
        <button
          className="intelligence-toggle"
          type="button"
          aria-expanded={false}
          aria-label="Ask PuckPulse"
          onClick={() => setOpen(true)}
        >
          <span aria-hidden="true">✦ </span>
          {/* Full label on desktop; just "Ask" on phones so it covers less content. */}
          <span className="intelligence-toggle-full" aria-hidden="true">Ask PuckPulse</span>
          <span className="intelligence-toggle-short" aria-hidden="true">Ask</span>
        </button>
      )}

      {open && (
        <>
          <div className="intelligence-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />
          <section className="intelligence-drawer" role="dialog" aria-label="PuckPulse AI chat" ref={drawerRef}>
            <header className="intelligence-header">
              <div>
                <strong>✦ PuckPulse AI</strong>
                <span className="intelligence-context">On: {label}</span>
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

            <div className="intelligence-thread" ref={threadRef} onScroll={onThreadScroll} aria-live="polite">
              {messages.length === 0 && (
                <div className="intelligence-empty">
                  <p>Ask about scores, standings, odds and bets, lineups, fantasy, players, or anything on this page.</p>
                  <div className="intelligence-suggestions">
                    {suggestions.map((s) => (
                      <button key={s} type="button" className="intelligence-suggestion" onClick={() => send(s)}>{s}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m) =>
                m.role === "divider" ? (
                  <p key={m.id} className="chat-divider">{m.content}</p>
                ) : m.role === "user" ? (
                  <div key={m.id} className="chat-msg chat-msg-user">{m.content}</div>
                ) : (
                  <div key={m.id} className="chat-msg chat-msg-ai">
                    {m.error ? (
                      <p className="intelligence-error">{m.error}</p>
                    ) : m.retryIn ? (
                      <p className="intelligence-typing" role="status">PuckPulse AI is busy right now. Trying again in {m.retryIn}s…</p>
                    ) : m.content ? (
                      <ChatMarkdown text={m.content} />
                    ) : (
                      <p className="intelligence-typing" role="status">{m.status || "Thinking…"}</p>
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
                aria-label="Question for PuckPulse AI"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  // Grow with the text (Safari lacks CSS field-sizing).
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                }}
                onKeyDown={onKeyDown}
                maxLength="1000"
                placeholder={messages.length ? "Ask a follow-up…" : "Ask anything about the NHL…"}
              />
              <button type="submit" aria-label="Send" disabled={loading || !input.trim()}>
                <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h12M10 4l6 6-6 6" /></svg>
              </button>
            </form>
            <p className="intelligence-footnote">AI answers from PuckPulse&apos;s data and models. It can make mistakes.</p>
          </section>
        </>
      )}
    </aside>
  );
}
