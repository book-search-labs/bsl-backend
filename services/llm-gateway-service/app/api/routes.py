import asyncio
import json
import math
import re
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.schemas import GenerateRequest, GenerateResponse
from app.core.audit import append_audit
from app.core.limiter import RateLimiter
from app.core.settings import SETTINGS

router = APIRouter()
rate_limiter = RateLimiter(SETTINGS.rate_limit_rpm)

state = {
    "spent_usd": 0.0,
    "spent_day": None,
}


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _charge_cost(tokens: int) -> float:
    return (tokens / 1000.0) * SETTINGS.cost_per_1k_tokens


def _check_budget(cost: float) -> None:
    if SETTINGS.cost_budget_usd <= 0:
        return
    if state["spent_usd"] + cost > SETTINGS.cost_budget_usd:
        raise HTTPException(status_code=429, detail={"code": "budget_exceeded", "message": "cost budget exceeded"})


def _apply_charge(cost: float) -> None:
    state["spent_usd"] += cost


def _synthesize_answer(payload: GenerateRequest) -> tuple[str, list[str]]:
    answer = ""
    citations: list[str] = []
    chunks = payload.context.chunks if payload.context else []
    if chunks:
        top = chunks[:2]
        citations = [chunk.citation_key for chunk in top]
        summary = " ".join(chunk.content[:160].strip() for chunk in top)
        answer = f"Based on the provided sources, {summary}"
        if payload.citations_required and citations:
            answer = f"{answer} [{' '.join(citations)}]"
    else:
        answer = "Insufficient evidence to answer the question with citations."
    return answer, citations


def _tokenize_for_stream(text: str) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"\S+\s*", text)
    return tokens if tokens else [text]


def _sse_event(name: str, data: dict | str) -> str:
    if isinstance(data, str):
        payload = data
    else:
        payload = json.dumps(data, ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"


def _audit_success(trace_id: str, request_id: str, model: str, tokens: int, cost: float) -> None:
    append_audit(
        SETTINGS.audit_log_path,
        {
            "trace_id": trace_id,
            "request_id": request_id,
            "model": model,
            "tokens": tokens,
            "cost_usd": cost,
            "status": "ok",
        },
    )


def _stream_generate(
    resolved_trace: str,
    resolved_request: str,
    model: str,
    answer: str,
    citations: list[str],
) -> AsyncIterator[str]:
    async def generator() -> AsyncIterator[str]:
        yield _sse_event(
            "meta",
            {
                "trace_id": resolved_trace,
                "request_id": resolved_request,
                "model": model,
            },
        )
        for token in _tokenize_for_stream(answer):
            yield _sse_event("delta", {"delta": token})
            if SETTINGS.stream_token_delay_ms > 0:
                await asyncio.sleep(SETTINGS.stream_token_delay_ms / 1000.0)
        yield _sse_event("done", {"status": "ok", "citations": citations})

    return generator()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    return {"status": "ok"}


@router.post("/v1/generate", response_model=GenerateResponse)
async def generate(
    payload: GenerateRequest,
    trace_id: Optional[str] = Header(default=None, alias="x-trace-id"),
    request_id: Optional[str] = Header(default=None, alias="x-request-id"),
    api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    stream: bool = Query(default=False),
):
    key = api_key or "anonymous"
    if SETTINGS.allowed_keys and key not in SETTINGS.allowed_keys:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "invalid api key"})
    if not rate_limiter.allow(key):
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": "rate limit exceeded"})

    resolved_trace = payload.trace_id or trace_id or str(uuid.uuid4())
    resolved_request = payload.request_id or request_id or str(uuid.uuid4())
    model = payload.model or SETTINGS.default_model

    answer, citations = _synthesize_answer(payload)
    tokens = _estimate_tokens(answer)
    cost = _charge_cost(tokens)
    _check_budget(cost)
    _apply_charge(cost)
    _audit_success(resolved_trace, resolved_request, model, tokens, cost)

    should_stream = bool(stream or payload.stream)
    if should_stream:
        return StreamingResponse(
            _stream_generate(resolved_trace, resolved_request, model, answer, citations),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache"},
        )

    return GenerateResponse(
        version="v1",
        trace_id=resolved_trace,
        request_id=resolved_request,
        model=model,
        content=answer,
        citations=citations,
        tokens=tokens,
        cost_usd=cost,
    )
