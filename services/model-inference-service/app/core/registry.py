import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelSpec:
    model_id: str
    task: str
    backend: str
    artifact_uri: str
    active: bool
    canary: bool
    canary_weight: float
    status: str
    updated_at: str
    input_name: Optional[str] = None
    output_name: Optional[str] = None
    feature_order: Optional[List[str]] = None
    tokenizer_uri: Optional[str] = None
    max_len: Optional[int] = None
    logit_index: Optional[int] = None

    def to_dict(self, loaded: bool) -> dict:
        return {
            "id": self.model_id,
            "task": self.task,
            "status": self.status,
            "backend": self.backend,
            "active": self.active,
            "canary": self.canary,
            "canary_weight": self.canary_weight,
            "artifact_uri": self.artifact_uri,
            "loaded": loaded,
            "updated_at": self.updated_at,
        }


class ModelRegistry:
    def __init__(self, path: str, refresh_ms: int) -> None:
        self._path = path
        self._refresh_ms = max(100, refresh_ms)
        self._last_loaded_at = 0.0
        self._last_mtime = 0.0
        self._models: Dict[str, ModelSpec] = {}
        self._by_task: Dict[str, List[ModelSpec]] = {}

    def load(self) -> None:
        if not os.path.exists(self._path):
            self._models = {}
            self._by_task = {}
            return
        with open(self._path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        models = {}
        by_task: Dict[str, List[ModelSpec]] = {}
        for item in payload.get("models", []):
            model = ModelSpec(
                model_id=item.get("id", ""),
                task=item.get("task", ""),
                backend=item.get("backend", "toy"),
                artifact_uri=item.get("artifact_uri", ""),
                active=bool(item.get("active", False)),
                canary=bool(item.get("canary", False)),
                canary_weight=float(item.get("canary_weight", 0.0)),
                status=item.get("status", "unknown"),
                updated_at=item.get("updated_at", ""),
                input_name=item.get("input_name"),
                output_name=item.get("output_name"),
                feature_order=item.get("feature_order"),
                tokenizer_uri=item.get("tokenizer_uri"),
                max_len=item.get("max_len"),
                logit_index=item.get("logit_index"),
            )
            if model.model_id:
                models[model.model_id] = model
                by_task.setdefault(model.task, []).append(model)

        self._models = models
        self._by_task = by_task
        self._last_loaded_at = time.time()
        self._last_mtime = os.path.getmtime(self._path)

    def maybe_reload(self) -> None:
        now = time.time()
        if now - self._last_loaded_at < (self._refresh_ms / 1000.0):
            return
        if not os.path.exists(self._path):
            return
        mtime = os.path.getmtime(self._path)
        if mtime != self._last_mtime:
            self.load()

    def list_models(self) -> List[ModelSpec]:
        self.maybe_reload()
        return list(self._models.values())

    def resolve(self, task: str, requested_id: Optional[str]) -> Optional[ModelSpec]:
        self.maybe_reload()
        if requested_id:
            return self._models.get(requested_id)
        candidates = self._by_task.get(task, [])
        active = [m for m in candidates if m.active]
        canary = [m for m in candidates if m.canary and m.canary_weight > 0]
        if canary:
            chosen = canary[0]
            if random.random() < chosen.canary_weight:
                return chosen
        return active[0] if active else (candidates[0] if candidates else None)
