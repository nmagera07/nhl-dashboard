"""
Tracing: every AI job (a chat question, a post draft, a pregame brief...)
becomes one trace in Langfuse, a timed tree of what happened:

    chat "Can the Leafs make the playoffs?"
    ├─ gemini            generation: messages in, reply out, tokens
    ├─ get_playoff_odds  tool: arguments in, JSON result out
    ├─ gemini            generation: failed (HTTP 429)
    └─ groq              generation: the answer

The usage log lines (usage.py) stay: they're how a day's tokens get added up
from the container logs. Traces are for looking at one request in detail.

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (the SDK also
reads LANGFUSE_BASE_URL and LANGFUSE_TRACING_ENVIRONMENT). When it's off, or
if Langfuse misbehaves, every call here does nothing: tracing must never
break or slow down an answer. The SDK sends in the background, in batches.

Spans are passed around explicitly (parent.child(...)) rather than through
OpenTelemetry's "current span": the chat agent is an async generator, and a
context set inside one isn't safe to carry across its yields. Jobs that are
plain coroutines use job(), which also makes the trace findable with current().
"""

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_client = None  # a langfuse.Langfuse, or None when tracing is off


class Span:
    """One step of a trace. Every method swallows errors from Langfuse."""

    def __init__(self, observation):
        self._observation = observation
        self._ended = False

    def child(self, name: str, as_type: str = "span", **fields) -> "Span":
        try:
            return Span(self._observation.start_observation(name=name, as_type=as_type, **fields))
        except Exception:  # noqa: BLE001
            logger.debug("Couldn't start span %s", name, exc_info=True)
            return NULL

    def update(self, **fields) -> None:
        try:
            self._observation.update(**fields)
        except Exception:  # noqa: BLE001
            logger.debug("Couldn't update span", exc_info=True)

    def end(self, **fields) -> None:
        """Finish the step (once; later calls are ignored), recording any last fields."""
        if self._ended:
            return
        self._ended = True
        if fields:
            self.update(**fields)
        try:
            self._observation.end()
        except Exception:  # noqa: BLE001
            logger.debug("Couldn't end span", exc_info=True)

    def fail(self, reason: str, level: str = "ERROR") -> None:
        self.end(level=level, status_message=reason)

    def __bool__(self) -> bool:
        return True


class _NullSpan(Span):
    """What every call gets when tracing is off: does nothing, costs nothing."""

    def __init__(self):
        super().__init__(None)

    def child(self, name, as_type="span", **fields):
        return self

    def update(self, **fields):
        pass

    def end(self, **fields):
        pass

    def __bool__(self) -> bool:
        return False


NULL = _NullSpan()
_current: ContextVar[Span] = ContextVar("ai_trace", default=NULL)


def configure(env: Mapping[str, str] = os.environ, client=None) -> bool:
    """Turn tracing on if Langfuse keys are set (or use a given client, for tests). Returns whether it's on."""
    global _client
    if client is not None:
        _client = client
        return True
    _client = None
    if not (env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY")):
        return False
    try:
        from langfuse import Langfuse
        _client = Langfuse(public_key=env["LANGFUSE_PUBLIC_KEY"], secret_key=env["LANGFUSE_SECRET_KEY"])
    except Exception:  # noqa: BLE001 -- no tracing is better than no service
        logger.warning("Langfuse failed to start; tracing is off", exc_info=True)
        return False
    logger.warning("Tracing to Langfuse is on")  # warning: the only level that reaches the logs
    return True


def disable() -> None:
    global _client
    _client = None


def shutdown() -> None:
    """Send what's still queued (on service shutdown)."""
    if _client is None:
        return
    try:
        _client.shutdown()
    except Exception:  # noqa: BLE001
        logger.debug("Langfuse shutdown failed", exc_info=True)


def start(name: str, **fields) -> Span:
    """A new trace: its root step. End it with .end(output=...)."""
    if _client is None:
        return NULL
    try:
        return Span(_client.start_observation(name=name, as_type="agent", **fields))
    except Exception:  # noqa: BLE001
        logger.debug("Couldn't start trace %s", name, exc_info=True)
        return NULL


def current() -> Span:
    """The trace job() opened around this code, or NULL."""
    return _current.get()


@contextmanager
def job(name: str, **fields):
    """A trace around a plain coroutine's work: `with tracing.job("post", input=...) as trace:`."""
    trace = start(name, **fields)
    token = _current.set(trace)
    try:
        yield trace
    except BaseException as exc:
        trace.fail(type(exc).__name__)
        raise
    finally:
        _current.reset(token)
        trace.end()


def now() -> datetime:
    return datetime.now(timezone.utc)


def usage_details(usage) -> dict[str, int] | None:
    """Langfuse's token fields from an OpenAI-style usage object."""
    if usage is None:
        return None
    return {"input": getattr(usage, "prompt_tokens", None) or 0,
            "output": getattr(usage, "completion_tokens", None) or 0}


def reply(message) -> dict:
    """A model's turn, readable in the trace: its text and any tool calls."""
    calls = [{"name": c.function.name, "arguments": _parsed(c.function.arguments)}
             for c in (getattr(message, "tool_calls", None) or [])]
    out: dict[str, Any] = {"content": getattr(message, "content", None)}
    if calls:
        out["tool_calls"] = calls
    return out


async def tool(parent: Span, runner, name: str, arguments) -> str:
    """Run one tool call (runner.run) as a step of the trace."""
    span = parent.child(name, as_type="tool", input=_parsed(arguments))
    try:
        result = await runner.run(name, arguments)
    except BaseException as exc:
        span.fail(type(exc).__name__)
        raise
    parsed = _parsed(result)
    if isinstance(parsed, dict) and "error" in parsed:
        span.end(output=parsed, level="WARNING", status_message=str(parsed["error"])[:200])
    else:
        span.end(output=parsed)
    return result


def _parsed(text):
    """JSON text as data (shows as a tree in Langfuse); anything else as-is."""
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text
