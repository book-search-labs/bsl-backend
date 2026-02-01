import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas import (
    EmbedRequest,
    EmbedResponse,
    ModelsResponse,
    ReadyResponse,
    ScoreRequest,
    ScoreResponse,
)
from app.core.settings import SETTINGS
from app.core.state import batcher, embed_manager, model_manager, registry, request_limiter

router = APIRouter()
logger = logging.getLogger(__name__)


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
            if spec.backend == "onnx_cross" and (pair.doc is None or pair.doc.strip() == ""):
                raise HTTPException(status_code=400, detail={"code": "doc_required", "message": "doc text required"})
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


@router.post("/v1/embed", response_model=EmbedResponse)
async def embed_v1(
    payload: EmbedRequest,
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    return await embed_handler(payload, trace_id, request_id)


@router.post("/embed", response_model=EmbedResponse)
async def embed_legacy(
    payload: dict,
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    request = EmbedRequest(
        model=payload.get("model"),
        texts=payload.get("texts") or [],
        normalize=payload.get("normalize", None),
        trace_id=payload.get("trace_id"),
        request_id=payload.get("request_id"),
    )
    return await embed_handler(request, trace_id, request_id)


async def embed_handler(
    payload: EmbedRequest,
    trace_id: Optional[str],
    request_id: Optional[str],
) -> EmbedResponse:
    resolved_trace = payload.trace_id or trace_id or str(uuid.uuid4())
    resolved_request = payload.request_id or request_id or str(uuid.uuid4())
    model = payload.model or SETTINGS.default_embed_model or embed_manager.model_id()
    normalize = SETTINGS.embed_normalize if payload.normalize is None else payload.normalize
    timeout_ms = SETTINGS.timeout_ms

    if not payload.texts:
        raise HTTPException(status_code=400, detail={"code": "empty_texts", "message": "texts is empty"})
    if len(payload.texts) > SETTINGS.embed_batch_size:
        raise HTTPException(
            status_code=413,
            detail={"code": "batch_too_large", "message": "embed batch too large"},
        )

    async with request_limiter.limit(timeout_ms):
        started = asyncio.get_running_loop().time()
        try:
            vectors = await asyncio.wait_for(
                asyncio.to_thread(embed_texts, payload.texts, normalize, model),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail={"code": "timeout", "message": "embed timeout"}) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "embed_error", "message": str(exc)}) from exc

        dim = len(vectors[0]) if vectors else SETTINGS.embed_dim
        took_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        logger.info(
            "embed model=%s batch=%s took_ms=%s",
            model,
            len(payload.texts),
            took_ms,
        )
        return EmbedResponse(
            version="v1",
            trace_id=resolved_trace,
            request_id=resolved_request,
            model=model,
            dim=dim,
            vectors=vectors,
        )


def embed_texts(texts: list, normalize: bool, model_id: str) -> list:
    model = embed_manager.get_model(model_id)
    return model.embed(texts, normalize)
