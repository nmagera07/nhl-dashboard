import pytest

from app import tracing


@pytest.fixture(autouse=True)
def no_real_tracing(monkeypatch):
    """Tests never send traces, even with Langfuse keys in the shell."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.disable()
    yield
    tracing.disable()
