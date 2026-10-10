from dataclasses import dataclass, field
import os

from .providers import Provider, providers_from_env


@dataclass(frozen=True)
class Settings:
    dashboard_api_url: str
    allowed_origins: list[str]
    providers: list[Provider] = field(default_factory=list)
    max_output_tokens: int = 600
    max_context_chars: int = 24000
    digest_token: str = ""  # shared secret: only the daily job may ask for a digest


def _env(name: str, legacy: str, default: str) -> str:
    """New AI_* name first, then the old OPENAI_* one, so existing deploys keep working."""
    return os.getenv(name) or os.getenv(legacy) or default


def get_settings() -> Settings:
    origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
    return Settings(
        dashboard_api_url=os.getenv(
            "NHL_DASHBOARD_API_URL",
            "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io",
        ).rstrip("/"),
        allowed_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        providers=providers_from_env(),
        max_output_tokens=int(_env("AI_MAX_OUTPUT_TOKENS", "OPENAI_MAX_OUTPUT_TOKENS", "600")),
        max_context_chars=int(_env("AI_MAX_CONTEXT_CHARS", "OPENAI_MAX_CONTEXT_CHARS", "24000")),
        digest_token=os.getenv("DIGEST_TOKEN", ""),
    )
