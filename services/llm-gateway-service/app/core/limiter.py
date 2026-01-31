import time
from collections import defaultdict, deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, rpm: int) -> None:
        self.rpm = max(1, rpm)
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        window = 60.0
        events = self._events[key]
        while events and now - events[0] > window:
            events.popleft()
        if len(events) >= self.rpm:
            return False
        events.append(now)
        return True
