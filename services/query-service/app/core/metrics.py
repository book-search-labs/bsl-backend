from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Mapping


class MetricRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._lock = Lock()

    def inc(self, name: str, labels: Mapping[str, str] | None = None, value: int = 1) -> None:
        key = self._format_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set(self, name: str, labels: Mapping[str, str] | None = None, value: float = 0.0) -> None:
        key = self._format_key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            merged: dict[str, float | int] = dict(self._counters)
            merged.update(self._gauges)
            return merged

    @staticmethod
    def _format_key(name: str, labels: Mapping[str, str] | None) -> str:
        if not labels:
            return name
        parts = [f"{k}={labels[k]}" for k in sorted(labels.keys())]
        return f"{name}{{{','.join(parts)}}}"


metrics = MetricRegistry()
