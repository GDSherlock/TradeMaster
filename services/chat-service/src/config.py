from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVICE_ROOT.parents[1]
ENV_FILE = PROJECT_ROOT / "config" / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("CHAT_SERVICE_HOST", "0.0.0.0")
    port: int = _int("CHAT_SERVICE_PORT", 8001)
    cors_allow_origins: list[str] = None  # type: ignore[assignment]

    rate_limit_per_minute: int = _int("CHAT_RATE_LIMIT_PER_MINUTE", 20)
    max_concurrency_per_ip: int = _int("CHAT_MAX_CONCURRENCY_PER_IP", 5)
    max_input_chars: int = _int("CHAT_MAX_INPUT_CHARS", 2000)
    max_turns: int = _int("CHAT_MAX_TURNS", 12)

    api_service_base_url: str = os.getenv("API_SERVICE_BASE_URL", "http://localhost:8000")
    api_service_token: str = os.getenv("API_SERVICE_TOKEN", "")

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-5.2")
    llm_api_key: str = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    llm_timeout_seconds: int = _int("LLM_TIMEOUT_SECONDS", 30)
    llm_max_output_chars: int = _int("LLM_MAX_OUTPUT_CHARS", 4000)

    database_url: str = os.getenv("DATABASE_URL", "")
    audit_log_path: str = os.getenv("CHAT_AUDIT_LOG", str(PROJECT_ROOT / "logs" / "chat_audit.jsonl"))
    temperature: float = _float("CHAT_TEMPERATURE", 0.2)

    def __post_init__(self) -> None:
        origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8088")
        object.__setattr__(self, "cors_allow_origins", [x.strip() for x in origins.split(",") if x.strip()])


settings = Settings()
