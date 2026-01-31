import asyncio
import math
import uuid
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas import ModelsResponse, ReadyResponse, ScoreRequest, ScoreResponse
from app.core.settings import SETTINGS
from app.core.state import batcher, model_manager, registry, request_limiter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
async def ready():
    models = registry.list_models()
    loaded = 0
    for model in models:
        if model_manager.is_loaded(model.model_id):
            loaded += 1
    status = "ok" if loaded > 0 else "degraded"
    return ReadyResponse(status=status, models_ready=loaded, models_total=len(models))


@router.get("/v1/models", response_model=ModelsResponse)
async def list_models(
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    resolved_trace = trace_id or str(uuid.uuid4())
    resolved_request = request_id or str(uuid.uuid4())
    models = []
    for model in registry.list_models():
        models.append(model.to_dict(model_manager.is_loaded(model.model_id)))
    return ModelsResponse(version="v1", trace_id=resolved_trace, request_id=resolved_request, models=models)


@router.post("/v1/score", response_model=ScoreResponse)
async def score(
    payload: ScoreRequest,
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    resolved_trace = payload.trace_id or trace_id or str(uuid.uuid4())
    resolved_request = payload.request_id or request_id or str(uuid.uuid4())

    timeout_ms = SETTINGS.timeout_ms
    if payload.options and payload.options.timeout_ms:
        timeout_ms = payload.options.timeout_ms

    async with request_limiter.limit(timeout_ms):
        task = payload.task or SETTINGS.default_task
        spec, model = model_manager.get_model(task, payload.model)
        if spec is None or model is None:
            raise HTTPException(status_code=503, detail={"code": "model_unavailable", "message": "model unavailable"})

        pairs = []
        for pair in payload.pairs:
            entry = {
                "pair_id": pair.pair_id,
                "query": pair.query,
                "doc": pair.doc,
                "doc_id": pair.doc_id,
            }
            if pair.features:
                entry["features"] = pair.features.model_dump(by_alias=True, exclude_none=True)
            pairs.append(entry)

        started = asyncio.get_running_loop().time()
        try:
            if batcher is not None:
                scores = await asyncio.wait_for(
                    batcher.submit(task, spec.model_id, pairs), timeout=timeout_ms / 1000.0
                )
                debug_items = None
            else:
                results = await asyncio.wait_for(
                    asyncio.to_thread(model.score, pairs), timeout=timeout_ms / 1000.0
                )
                scores = [item.score for item in results]
                debug_items = [item.debug for item in results]
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail={"code": "timeout", "message": "score timeout"}) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "model_error", "message": str(exc)}) from exc

        took_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        debug = None
        if payload.options and payload.options.return_debug:
            debug = {
                "backend": spec.backend,
                "model_id": spec.model_id,
            }
            if debug_items is not None:
                debug["items"] = debug_items

        return ScoreResponse(
            version="v1",
            trace_id=resolved_trace,
            request_id=resolved_request,
            model=spec.model_id,
            took_ms=took_ms,
            scores=scores,
            debug=debug,
        )


@router.post("/embed")
async def embed(
    payload: dict,
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    resolved_trace = payload.get("trace_id") or trace_id or str(uuid.uuid4())
    resolved_request = payload.get("request_id") or request_id or str(uuid.uuid4())
    texts = payload.get("texts") or []
    model = payload.get("model") or "toy_embed_v1"
    vectors = [toy_embed(text or "") for text in texts]
    return {
        "version": "v1",
        "trace_id": resolved_trace,
        "request_id": resolved_request,
        "model": model,
        "vectors": vectors,
    }


def toy_embed(text: str, dim: int = 1024) -> list:
    import hashlib
    import random

    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()[:8]
    seed = int.from_bytes(seed_bytes, "big", signed=False)
    rng = random.Random(seed)
    values = [rng.random() for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
