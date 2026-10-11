import * as Sentry from "@sentry/react";

// Real-user timing for PuckPulse AI: how long until the first status line
// ("Checking the standings…"), and until the answer is in. Sent to Sentry
// as a span with those numbers as attributes, so its dashboards can show
// p75/p95 for real visitors (cold starts included), not just our tests.
export function startChatTimer({ now = () => performance.now(), report = reportToSentry } = {}) {
  const started = now();
  let firstStatus = null;
  let firstText = null;
  let tools = 0;
  return {
    status() {
      tools += 1;
      if (firstStatus === null) firstStatus = now() - started;
    },
    text() {
      if (firstText === null) firstText = now() - started;
    },
    finish({ error = false } = {}) {
      const timing = {
        "chat.first_status_ms": firstStatus === null ? null : Math.round(firstStatus),
        "chat.first_text_ms": firstText === null ? null : Math.round(firstText),
        "chat.total_ms": Math.round(now() - started),
        "chat.tool_calls": tools,
        "chat.error": error,
      };
      report(timing, started);
      return timing;
    },
  };
}

function reportToSentry(timing) {
  // A no-op when Sentry isn't initialized (no DSN, e.g. local dev).
  const span = Sentry.startInactiveSpan({ name: "PuckPulse AI answer", op: "ui.chat", forceTransaction: true });
  Object.entries(timing).forEach(([key, value]) => value !== null && span?.setAttribute(key, value));
  span?.end();
}
