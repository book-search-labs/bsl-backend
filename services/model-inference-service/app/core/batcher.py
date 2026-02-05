import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.core.model_manager import ModelManager


@dataclass
class BatchItem:
    key: Tuple[str, str]
    pairs: List[dict]
    future: asyncio.Future


class DynamicBatcher:
    def __init__(self, manager: ModelManager, batch_window_ms: int, batch_max_pairs: int) -> None:
        self._manager = manager
        self._queue: asyncio.Queue[BatchItem] = asyncio.Queue()
        self._window_ms = max(1, batch_window_ms)
        self._max_pairs = max(1, batch_max_pairs)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._batch_loop())

    async def submit(self, task: str, model_id: str, pairs: List[dict]) -> List[float]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self._queue.put(BatchItem(key=(task, model_id), pairs=pairs, future=future))
        return await future

    async def _batch_loop(self) -> None:
        while True:
            item = await self._queue.get()
            batch = [item]
            key = item.key
            total_pairs = len(item.pairs)
            deadline = time.monotonic() + (self._window_ms / 1000.0)

            while total_pairs < self._max_pairs:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    next_item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if next_item.key != key:
                    await self._queue.put(next_item)
                    break
                batch.append(next_item)
                total_pairs += len(next_item.pairs)

            spec, model = self._manager.get_model(key[0], key[1])
            if model is None:
                for entry in batch:
                    if not entry.future.done():
                        entry.future.set_exception(RuntimeError("model_not_ready"))
                continue

            combined: List[dict] = []
            spans = []
            for entry in batch:
                start = len(combined)
                combined.extend(entry.pairs)
                spans.append((entry.future, start, len(combined)))

            results = await asyncio.to_thread(model.score, combined)
            scores = [item.score for item in results]
            for future, start, end in spans:
                if not future.done():
                    future.set_result(scores[start:end])
