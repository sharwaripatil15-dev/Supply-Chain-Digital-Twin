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
    # /weather/*: true = never call the weather providers (Live mode serves the last disk cache, else calm "simulated"
    # weather). Defaults to false because the providers are free and keyless; tests switch it on.
    mock_weather: bool = field(default_factory=lambda: _bool("USE_MOCK_WEATHER", False))

    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_SECONDS", "300")))
    cors_origins: list[str] = field(
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )
    # Where the active network is persisted (data/active_network.json). Tests point this at a temp dir.
    data_dir: str = field(default_factory=lambda: os.getenv("AEGIS_DATA_DIR", str(_HERE / "data")))
    max_upload_bytes: int = 2_000_000

    # Weather and hazard providers (free, no key). OPENMETEO_API_KEY switches to the customer endpoints.
    openmeteo_api_key: str = field(default_factory=lambda: os.getenv("OPENMETEO_API_KEY", ""))
    openmeteo_forecast_url: str = field(default_factory=lambda: os.getenv("OPENMETEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"))
    openmeteo_flood_url: str = field(default_factory=lambda: os.getenv("OPENMETEO_FLOOD_URL", "https://flood-api.open-meteo.com/v1/flood"))
    openmeteo_marine_url: str = field(default_factory=lambda: os.getenv("OPENMETEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine"))
    usgs_quake_url: str = field(
        default_factory=lambda: os.getenv("USGS_QUAKE_URL", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson")
    )
    gdacs_url: str = field(
        default_factory=lambda: os.getenv("GDACS_URL", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH")
    )
    weather_timeout_s: float = field(default_factory=lambda: float(os.getenv("WEATHER_TIMEOUT_S", "5")))
    weather_retries: int = 2
    weather_cache_ttl: int = field(default_factory=lambda: int(os.getenv("WEATHER_CACHE_TTL", "1800")))  # 30 min
    weather_min_refresh_s: int = 600  # fair use: a manual refresh re-fetches at most every 10 minutes
    weather_max_cells: int = 60  # grid cells per refresh (each a coordinate in a batched request)
    weather_user_agent: str = "AEGIS-SupplyChainTwin/0.2 (+https://open-meteo.com fair use)"
    default_seed: int = 7
    default_horizon: int = 30

    def mock_flags(self) -> dict[str, bool]:
        return {
            "network": self.mock_network,
            "simulate": self.mock_simulate,
            "chaos": self.mock_chaos,
            "recover": self.mock_recover,
            "parse": self.mock_parse,
            "weather": self.mock_weather,
        }


settings = Settings()
