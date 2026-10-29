"""
Token usage: one log line per AI call, tagged with what it was for, so a
day's tokens can be added up per purpose and provider from the logs
(Log Analytics, ContainerAppConsoleLogs_CL):

    AI usage: purpose=brief provider=groq model=openai/gpt-oss-120b prompt=4120 completion=380

The purpose is set around each job (with usage.purpose("brief"): ...) and
rides along to the provider chain in a context variable, so every turn of
an agent loop, fallbacks included, is counted under it.
"""

import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger("app.usage")
# The service configures no logging, so only warnings reach the container's
# logs (Python's last-resort handler). These lines are INFO: give them their own.
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# Untagged calls are the chat agent's: it streams from an async generator,
# where setting a context variable across yields isn't safe.
_purpose: ContextVar[str] = ContextVar("ai_purpose", default="chat")


@contextmanager
def purpose(name: str):
    token = _purpose.set(name)
    try:
        yield
    finally:
        _purpose.reset(token)


def record(provider, usage) -> None:
    """Log one call's tokens (providers that send no usage are skipped)."""
    if usage is None:
        return
    prompt = getattr(usage, "prompt_tokens", None) or 0
    completion = getattr(usage, "completion_tokens", None) or 0
    logger.info("AI usage: purpose=%s provider=%s model=%s prompt=%d completion=%d",
                _purpose.get(), provider.name, provider.model, prompt, completion)
