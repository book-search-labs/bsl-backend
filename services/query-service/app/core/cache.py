from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import Any

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

logger = logging.getLogger(__name__)


class MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at <= now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = None
        if ttl is not None:
            expires_at = time.time() + ttl
        with self._lock:
            self._store[key] = (expires_at, value)

    def setnx(self, key: str, value: Any, ttl: int | None = None) -> bool:
        now = time.time()
        expires_at = None
        if ttl is not None:
            expires_at = now + ttl
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                entry_exp, _ = entry
                if entry_exp is None or entry_exp > now:
                    return False
            self._store[key] = (expires_at, value)
            return True

    def incr(self, key: str, ttl: int | None = None) -> int:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None or (entry[0] is not None and entry[0] <= now):
                value = 1
            else:
                _, current = entry
                value = int(current) + 1
            expires_at = None
            if ttl is not None:
                expires_at = now + ttl
            self._store[key] = (expires_at, value)
            return value


class CacheClient:
    def __init__(self, redis_url: str | None) -> None:
        self._redis = None
        self._local = MemoryCache()
        self._redis_enabled = False
        if redis_url and redis is not None:
            try:
                self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
                self._redis_enabled = True
            except Exception:
                self._redis = None
                self._redis_enabled = False

    def get_json(self, key: str) -> Any | None:
        if self._redis_enabled and self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is None:
                    return None
                return json.loads(value)
            except Exception as exc:
                logger.warning("cache redis get failed: %s", exc)
                _metrics_inc("qs_cache_errors_total")
        return self._local.get(key)

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._redis_enabled and self._redis is not None:
            try:
                payload = json.dumps(value, ensure_ascii=False)
                if ttl is not None:
                    self._redis.setex(key, ttl, payload)
                else:
                    self._redis.set(key, payload)
                return
            except Exception as exc:
                logger.warning("cache redis set failed: %s", exc)
                _metrics_inc("qs_cache_errors_total")
        self._local.set(key, value, ttl)

    def setnx(self, key: str, value: str, ttl: int | None = None) -> bool:
        if self._redis_enabled and self._redis is not None:
            try:
                result = self._redis.set(name=key, value=value, nx=True, ex=ttl)
                return bool(result)
            except Exception as exc:
                logger.warning("cache redis setnx failed: %s", exc)
                _metrics_inc("qs_cache_errors_total")
        return self._local.setnx(key, value, ttl)

    def incr(self, key: str, ttl: int | None = None) -> int:
        if self._redis_enabled and self._redis is not None:
            try:
                value = self._redis.incr(key)
                if ttl is not None:
                    self._redis.expire(key, ttl)
                return int(value)
            except Exception as exc:
                logger.warning("cache redis incr failed: %s", exc)
                _metrics_inc("qs_cache_errors_total")
        return self._local.incr(key, ttl)


_cache: CacheClient | None = None


def get_cache() -> CacheClient:
    global _cache
    if _cache is not None:
        return _cache
    redis_url = os.getenv("REDIS_URL")
    _cache = CacheClient(redis_url)
    return _cache


def _metrics_inc(name: str) -> None:
    try:
        from app.core.metrics import metrics

        metrics.inc(name)
    except Exception:
        return
