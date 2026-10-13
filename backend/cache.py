"""Tiny JSON cache: in-memory TTL dict, with an optional Redis backend if REDIS_URL is reachable."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

from fastapi.encoders import jsonable_encoder

from config import settings

log = logging.getLogger("aegis.cache")


class Cache:
    def __init__(self, ttl: int, redis_url: str = "") -> None:
        self.ttl = ttl
        self._mem: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._redis = None
        if redis_url:
            try:
                import redis

                client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
                client.ping()
                self._redis = client
                log.info("cache: using Redis at %s", redis_url)
            except Exception as exc:  # Redis is optional; fall back silently
                log.info("cache: Redis unavailable (%s), using in-memory cache", exc)

    @staticmethod
    def key(prefix: str, payload: Any = None) -> str:
        blob = json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":"))
        return f"aegis:{prefix}:{hashlib.sha1(blob.encode()).hexdigest()[:16]}"

    def get(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                pass
        with self._lock:
            hit = self._mem.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
            self._mem.pop(key, None)
        return None

    def set(self, key: str, value: Any) -> None:
        value = jsonable_encoder(value)
        if self._redis is not None:
            try:
                self._redis.setex(key, self.ttl, json.dumps(value))
                return
            except Exception:
                pass
        with self._lock:
            self._mem[key] = (time.time() + self.ttl, value)

    def get_or_compute(self, key: str, fn: Callable[[], Any]) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = jsonable_encoder(fn())
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()


cache = Cache(settings.cache_ttl_seconds, settings.redis_url)
