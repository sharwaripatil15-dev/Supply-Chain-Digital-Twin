"""Async clients for the free hazard data sources, normalised into one `HazardSample` per location and day.

Sources (base URLs in config.py; no keys needed):
    forecast  Open-Meteo forecast: daily rain, rain probability, wind gusts, max temperature, weather code;
              hourly visibility (reduced to a daily "fog" visibility, see `_fog_visibility`)
    flood     Open-Meteo flood (GloFAS): river discharge and its long-run mean -> discharge ratio
    marine    Open-Meteo marine: daily max wave height and wave period (sea lanes and port sites only)
    quakes    USGS M4.5+ past-week GeoJSON feed, filtered to the India region
    gdacs     optional GDACS tropical-cyclone alerts (overlay only); any failure is skipped silently

Reliability: every call is async with a 5 s timeout, 2 retries with backoff, a User-Agent, a per-provider rate limiter
and batching (all Open-Meteo APIs take comma-separated coordinate lists). Responses are cached in memory (and Redis if
configured) for 30 minutes and on disk (DATA_DIR/weather_cache/) so the last good answer still works offline.
`fetch_json` never raises a network error to the caller: it returns the cached copy (quality "cached") or a
ProviderError the service turns into data_quality "unavailable" for that provider.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from cache import Cache
from config import settings

log = logging.getLogger("aegis.weather")

INDIA_BBOX = (5.0, 66.0, 38.0, 99.0)  # lat_min, lon_min, lat_max, lon_max
BATCH = 50  # coordinates per Open-Meteo request
RATE_INTERVAL_S = 0.25  # min gap between two requests to the same provider
IST = timezone(timedelta(hours=5, minutes=30))

Cell = tuple[float, float]


@dataclass
class HazardSample:
    """Weather and hazard values at one location on one day. None = not measured by any provider."""

    lat: float
    lon: float
    date: str
    rain_mm: float | None = None
    rain_prob: float | None = None  # 0..1
    wind_gust_kmh: float | None = None
    visibility_m: float | None = None
    temp_c: float | None = None
    river_discharge_ratio: float | None = None
    wave_height_m: float | None = None
    quake_magnitude: float | None = None
    quake_distance_km: float | None = None
    source: str = "open-meteo"
    quality: str = "live"

    def to_dict(self) -> dict:
        return asdict(self)


class ProviderError(RuntimeError):
    """A provider could not be reached and had no cached answer."""


@dataclass
class Fetched:
    data: Any
    quality: str  # live | cached
    fetched_at: float


@dataclass
class ProviderStatus:
    name: str
    ok: bool | None = None  # None = not called yet
    quality: str | None = None
    last_success: float | None = None
    last_error: str | None = None
    calls: int = 0
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ transport
class RateLimiter:
    """At most one request per `interval` seconds for a provider (fair use)."""

    def __init__(self, interval: float = RATE_INTERVAL_S):
        self.interval = interval
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


_limiters: dict[str, RateLimiter] = {}
STATUS: dict[str, ProviderStatus] = {p: ProviderStatus(p) for p in ("forecast", "flood", "marine", "quakes", "gdacs")}
_mem = Cache(settings.weather_cache_ttl, settings.redis_url)

# Tests replace this with a factory that returns a client on an httpx.MockTransport (never the real network).
client_factory: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(  # noqa: E731
    timeout=settings.weather_timeout_s, headers={"User-Agent": settings.weather_user_agent}, follow_redirects=True
)


def cache_dir() -> Path:
    path = Path(settings.data_dir) / "weather_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(provider: str, url: str, params: dict) -> str:
    blob = json.dumps([provider, url, params], sort_keys=True, default=str)
    return f"{provider}_{hashlib.sha1(blob.encode()).hexdigest()[:16]}"


def _disk_read(key: str) -> dict | None:
    path = cache_dir() / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _disk_write(key: str, data: Any, fetched_at: float) -> None:
    path = cache_dir() / f"{key}.json"
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps({"fetched_at": fetched_at, "data": data}), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # a read-only disk must not break a live answer
        log.info("weather: could not write disk cache (%s)", exc)


async def fetch_json(provider: str, url: str, params: dict | None = None, *, force: bool = False) -> Fetched:
    """GET JSON with cache -> network (retries) -> disk fallback. Raises ProviderError only when all three fail."""
    params = dict(params or {})
    if settings.openmeteo_api_key and "open-meteo.com" in url:
        params["apikey"] = settings.openmeteo_api_key
    key = _cache_key(provider, url, {k: v for k, v in params.items() if k != "apikey"})
    status = STATUS.setdefault(provider, ProviderStatus(provider))
    if not force:
        hit = _mem.get(f"aegis:weather:{key}")
        if hit is not None:
            return Fetched(hit["data"], "live", hit["fetched_at"])

    last_error = "not attempted"
    if not settings.mock_weather:
        limiter = _limiters.setdefault(provider, RateLimiter())
        async with client_factory() as client:
            for attempt in range(settings.weather_retries + 1):
                await limiter.wait()
                status.calls += 1
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                    resp.raise_for_status()
                    data = resp.json()
                    now = time.time()
                    _mem.set(f"aegis:weather:{key}", {"data": data, "fetched_at": now})
                    _disk_write(key, data, now)
                    status.ok, status.quality, status.last_success, status.last_error = True, "live", now, None
                    return Fetched(data, "live", now)
                except httpx.HTTPStatusError as exc:
                    last_error = str(exc)
                    if exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                        break  # a bad request will not get better with retries
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"[:200]
                if attempt < settings.weather_retries:
                    await asyncio.sleep(0.4 * (2**attempt))
    else:
        last_error = "live weather disabled (USE_MOCK_WEATHER=true)"

    disk = _disk_read(key)
    status.ok, status.last_error = False, last_error
    if disk is not None:
        status.quality = "cached"
        return Fetched(disk["data"], "cached", disk.get("fetched_at", 0.0))
    status.quality = "unavailable"
    raise ProviderError(f"{provider}: {last_error}")


# ------------------------------------------------------------------ normalisation (pure, unit-tested)
def _as_list(payload: Any) -> list[dict]:
    """Open-Meteo returns an object for one coordinate and a list for several."""
    if isinstance(payload, list):
        return payload
    return [payload] if isinstance(payload, dict) else []


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _fog_visibility(hourly_vis: list[Any]) -> float | None:
    """A day's fog visibility: the mean of its 4 lowest hourly readings (fog that lasts a morning, not one blip)."""
    vals = sorted(v for v in (_num(x) for x in hourly_vis) if v is not None)
    if not vals:
        return None
    low = vals[:4]
    return round(sum(low) / len(low), 1)


def normalize_forecast(payload: Any, cells: list[Cell]) -> dict[Cell, list[HazardSample]]:
    """Open-Meteo forecast response (one or many locations) -> {cell: [HazardSample per day]}."""
    out: dict[Cell, list[HazardSample]] = {}
    for cell, loc in zip(cells, _as_list(payload)):
        daily = loc.get("daily") or {}
        dates = daily.get("time") or []
        hourly = loc.get("hourly") or {}
        vis_by_date: dict[str, list] = {}
        for t, v in zip(hourly.get("time") or [], hourly.get("visibility") or []):
            vis_by_date.setdefault(str(t)[:10], []).append(v)
        rows = []
        for i, d in enumerate(dates):
            pick = lambda k: _num((daily.get(k) or [None] * len(dates))[i]) if i < len(daily.get(k) or []) else None  # noqa: E731
            prob = pick("precipitation_probability_max")
            rows.append(HazardSample(
                lat=cell[0], lon=cell[1], date=str(d),
                rain_mm=pick("precipitation_sum"),
                rain_prob=None if prob is None else round(prob / 100.0, 2),
                wind_gust_kmh=pick("wind_gusts_10m_max"),
                temp_c=pick("temperature_2m_max"),
                visibility_m=_fog_visibility(vis_by_date.get(str(d), [])),
                source="open-meteo forecast",
            ))
        out[cell] = rows
    return out


def normalize_flood(payload: Any, cells: list[Cell]) -> dict[Cell, dict[str, float]]:
    """Open-Meteo flood response -> {cell: {date: river discharge / its mean}}; cells without a river are skipped."""
    out: dict[Cell, dict[str, float]] = {}
    for cell, loc in zip(cells, _as_list(payload)):
        daily = loc.get("daily") or {}
        q = daily.get("river_discharge") or []
        mean = daily.get("river_discharge_mean") or []
        ratios = {}
        for i, d in enumerate(daily.get("time") or []):
            qv = _num(q[i]) if i < len(q) else None
            mv = _num(mean[i]) if i < len(mean) else None
            if qv is not None and mv:
                ratios[str(d)] = round(qv / mv, 2)
        if ratios:
            out[cell] = ratios
    return out


def normalize_marine(payload: Any, cells: list[Cell]) -> dict[Cell, dict[str, float]]:
    """Open-Meteo marine response -> {cell: {date: max wave height m}}; land cells (all null) are skipped."""
    out: dict[Cell, dict[str, float]] = {}
    for cell, loc in zip(cells, _as_list(payload)):
        daily = loc.get("daily") or {}
        waves = daily.get("wave_height_max") or []
        vals = {str(d): v for d, v in ((d, _num(waves[i]) if i < len(waves) else None) for i, d in enumerate(daily.get("time") or []))
                if v is not None}
        if vals:
            out[cell] = vals
    return out


def normalize_quakes(payload: Any, bbox: tuple[float, float, float, float] = INDIA_BBOX) -> list[dict]:
    """USGS GeoJSON -> [{lat, lon, magnitude, date, place, depth_km}] inside `bbox`."""
    lat0, lon0, lat1, lon1 = bbox
    out = []
    for f in (payload or {}).get("features") or []:
        try:
            lon, lat, *rest = f["geometry"]["coordinates"]
            props = f.get("properties") or {}
            mag = float(props["mag"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            continue
        when = datetime.fromtimestamp((props.get("time") or 0) / 1000, tz=IST).date().isoformat()
        out.append({"lat": float(lat), "lon": float(lon), "magnitude": mag, "date": when,
                    "place": str(props.get("place") or ""), "depth_km": float(rest[0]) if rest else None})
    return out


def normalize_gdacs(payload: Any, bbox: tuple[float, float, float, float] = INDIA_BBOX) -> list[dict]:
    """GDACS event list -> [{lat, lon, name, alert}] tropical cyclones near the region (best effort)."""
    lat0, lon0, lat1, lon1 = bbox
    out = []
    for f in (payload or {}).get("features") or []:
        try:
            lon, lat = f["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        props = f.get("properties") or {}
        if props.get("eventtype") not in (None, "TC") or not (lat0 - 5 <= lat <= lat1 and lon0 <= lon <= lon1 + 5):
            continue
        out.append({"lat": float(lat), "lon": float(lon), "name": str(props.get("name") or props.get("eventname") or "Cyclone"),
                    "alert": str(props.get("alertlevel") or "")})
    return out


# ------------------------------------------------------------------ provider calls
def _chunks(cells: list[Cell], n: int = BATCH) -> Iterable[list[Cell]]:
    for i in range(0, len(cells), n):
        yield cells[i:i + n]


def _coords(cells: list[Cell]) -> dict:
    return {"latitude": ",".join(f"{c[0]:.2f}" for c in cells), "longitude": ",".join(f"{c[1]:.2f}" for c in cells)}


async def _batched(provider: str, url: str, cells: list[Cell], params: dict, normalize, force: bool):
    """Run one request per batch; returns (merged result, worst quality, error or None). Partial failures keep the rest."""
    merged: dict = {}
    qualities: list[str] = []
    errors: list[str] = []
    for chunk in _chunks(cells):
        try:
            got = await fetch_json(provider, url, {**_coords(chunk), **params}, force=force)
            merged.update(normalize(got.data, chunk))
            qualities.append(got.quality)
        except ProviderError as exc:
            errors.append(str(exc))
            qualities.append("unavailable")
    quality = "unavailable" if not qualities or all(q == "unavailable" for q in qualities) else (
        "live" if all(q == "live" for q in qualities) else "cached" if "unavailable" not in qualities else "partial")
    return merged, quality, ("; ".join(errors) or None)


async def fetch_forecast(cells: list[Cell], days: int, force: bool = False):
    params = {
        "daily": "precipitation_sum,precipitation_probability_max,wind_gusts_10m_max,temperature_2m_max,weather_code",
        "hourly": "visibility", "forecast_days": max(1, min(16, days)), "timezone": "Asia/Kolkata",
    }
    url = settings.openmeteo_forecast_url
    if settings.openmeteo_api_key:
        url = url.replace("://api.", "://customer-api.")
    return await _batched("forecast", url, cells, params, normalize_forecast, force)


async def fetch_flood(cells: list[Cell], days: int, force: bool = False):
    params = {"daily": "river_discharge,river_discharge_mean", "forecast_days": max(1, min(30, days))}
    url = settings.openmeteo_flood_url
    if settings.openmeteo_api_key:
        url = url.replace("://flood-api.", "://customer-flood-api.")
    return await _batched("flood", url, cells, params, normalize_flood, force)


async def fetch_marine(cells: list[Cell], days: int, force: bool = False):
    params = {"daily": "wave_height_max,wave_period_max", "forecast_days": max(1, min(16, days)), "timezone": "Asia/Kolkata"}
    url = settings.openmeteo_marine_url
    if settings.openmeteo_api_key:
        url = url.replace("://marine-api.", "://customer-marine-api.")
    return await _batched("marine", url, cells, params, normalize_marine, force)


async def fetch_quakes(force: bool = False):
    try:
        got = await fetch_json("quakes", settings.usgs_quake_url, {}, force=force)
        return normalize_quakes(got.data), got.quality, None
    except ProviderError as exc:
        return [], "unavailable", str(exc)


async def fetch_gdacs(force: bool = False) -> list[dict]:
    """Optional cyclone alerts: any failure (network, format, anything) is skipped silently."""
    try:
        today = date.today()
        got = await fetch_json("gdacs", settings.gdacs_url, {
            "eventlist": "TC", "fromdate": (today - timedelta(days=3)).isoformat(), "todate": today.isoformat(),
        }, force=force)
        return normalize_gdacs(got.data)
    except Exception as exc:  # noqa: BLE001 - optional feed, never fatal
        log.info("weather: GDACS skipped (%s)", exc)
        return []


def provider_status() -> list[dict]:
    now = time.time()
    return [{
        "provider": s.name, "ok": s.ok, "quality": s.quality, "calls": s.calls, "last_error": s.last_error,
        "last_success": datetime.fromtimestamp(s.last_success, tz=IST).isoformat() if s.last_success else None,
        "cache_age_s": round(now - s.last_success) if s.last_success else None,
    } for s in STATUS.values()]


def reset_state() -> None:
    """Forget in-memory cache and provider status (tests)."""
    _mem.clear()
    for name in list(STATUS):
        STATUS[name] = ProviderStatus(name)
