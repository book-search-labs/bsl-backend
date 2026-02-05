import asyncio
from contextlib import asynccontextmanager
from fastapi import HTTPException


class RequestLimiter:
    def __init__(self, max_concurrency: int, max_queue: int) -> None:
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._max_queue = max(0, max_queue)
        self._pending = 0
        self._lock = asyncio.Lock()

    async def _reserve_slot(self) -> None:
        async with self._lock:
            if self._pending >= self._max_queue:
                raise HTTPException(status_code=429, detail={"code": "overloaded", "message": "queue full"})
            self._pending += 1

    async def _release_slot(self) -> None:
        async with self._lock:
            self._pending = max(0, self._pending - 1)

    @asynccontextmanager
    async def limit(self, timeout_ms: int):
        await self._reserve_slot()
        try:
            timeout_sec = max(timeout_ms, 1) / 1000.0 if timeout_ms else None
            if timeout_sec:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout_sec)
            else:
                await self._semaphore.acquire()
        except asyncio.TimeoutError as exc:
            await self._release_slot()
            raise HTTPException(status_code=504, detail={"code": "queue_timeout", "message": "queue timeout"}) from exc
        try:
            yield
        finally:
            self._semaphore.release()
            await self._release_slot()
