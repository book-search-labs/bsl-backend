from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

from app.core.settings import Settings


@dataclass
class BudgetManager:
    max_usd: float
    redis_url: str = ""
    window_sec: int = 0
    key: str = "llm:budget:global"

    def __post_init__(self) -> None:
        self._spent_usd = 0.0
        self._redis = None
        self._incr_script = None
        if self.redis_url:
            if redis is None:
                raise RuntimeError("redis dependency is required when LLM_REDIS_URL is set")
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._incr_script = self._redis.register_script(
                """
                local key = KEYS[1]
                local delta = tonumber(ARGV[1])
                local ttl = tonumber(ARGV[2])
                local next = redis.call("INCRBYFLOAT", key, delta)
                if ttl > 0 then
                  local ttl_now = redis.call("TTL", key)
                  if ttl_now < 0 then
                    redis.call("EXPIRE", key, ttl)
                  end
                end
                return next
                """
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "BudgetManager":
        return cls(
            max_usd=settings.cost_budget_usd,
            redis_url=settings.redis_url,
            window_sec=max(0, settings.budget_window_sec),
            key=settings.budget_key,
        )

    def enabled(self) -> bool:
        return self.max_usd > 0

    def current(self) -> float:
        if not self.enabled():
            return 0.0
        if self._redis:
            raw = self._redis.get(self.key)
            if raw is None:
                return 0.0
            try:
                return float(raw)
            except ValueError:
                return 0.0
        return self._spent_usd

    def can_spend(self, cost: float) -> bool:
        if not self.enabled() or cost <= 0:
            return True
        return (self.current() + cost) <= self.max_usd

    def spend(self, cost: float) -> None:
        if not self.enabled() or cost <= 0:
            return
        if self._redis:
            if not self._incr_script:
                raise RuntimeError("redis budget script not initialized")
            self._incr_script(keys=[self.key], args=[cost, self.window_sec])
            return
        self._spent_usd = max(0.0, self._spent_usd + cost)
