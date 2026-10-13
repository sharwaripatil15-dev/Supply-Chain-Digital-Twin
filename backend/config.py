"""Runtime configuration, read once from the environment (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env first, then the repo-root .env (neither is required).
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")
load_dotenv(_HERE.parent / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _mock(name: str) -> bool:
    return _bool(f"USE_MOCK_{name}", True)


@dataclass
class Settings:
    # Per-router mock switches: true = serve mock/mock_data.py, false = call core/.
    mock_network: bool = field(default_factory=lambda: _mock("NETWORK"))  # /network, /forecast, /surrogate
    mock_simulate: bool = field(default_factory=lambda: _mock("SIMULATE"))  # /simulate, /montecarlo
    mock_chaos: bool = field(default_factory=lambda: _mock("CHAOS"))  # /chaos
    mock_recover: bool = field(default_factory=lambda: _mock("RECOVER"))  # /recover
    mock_parse: bool = field(default_factory=lambda: _mock("PARSE"))  # /parse

    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "claude").lower())
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"))
    llm_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "8.0")))
    max_prompt_chars: int = field(default_factory=lambda: int(os.getenv("MAX_PROMPT_CHARS", "500")))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_SECONDS", "300")))
    cors_origins: list[str] = field(
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )
    # Where the active network is persisted (data/active_network.json). Tests point this at a temp dir.
    data_dir: str = field(default_factory=lambda: os.getenv("AEGIS_DATA_DIR", str(_HERE / "data")))
    max_upload_bytes: int = 2_000_000
    default_seed: int = 7
    default_horizon: int = 30

    def mock_flags(self) -> dict[str, bool]:
        return {
            "network": self.mock_network,
            "simulate": self.mock_simulate,
            "chaos": self.mock_chaos,
            "recover": self.mock_recover,
            "parse": self.mock_parse,
        }


settings = Settings()
