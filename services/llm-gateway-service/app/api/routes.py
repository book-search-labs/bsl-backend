import asyncio
import json
import math
import logging
import re
import uuid
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.schemas import GenerateRequest, GenerateResponse
from app.core.audit import append_audit
from app.core.audit_db import append_audit_db
from app.core.budget import BudgetManager
from app.core.limiter import RateLimiter
from app.core.settings import SETTINGS

router = APIRouter()
logger = logging.getLogger(__name__)
rate_limiter = RateLimiter(SETTINGS.rate_limit_rpm)
budget_manager = BudgetManager.from_settings(SETTINGS)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _charge_cost(tokens: int) -> float:
    return (tokens / 1000.0) * SETTINGS.cost_per_1k_tokens


def _check_budget(cost: float) -> None:
    if cost <= 0 or not budget_manager.enabled():
        return
    if not budget_manager.can_spend(cost):
        raise HTTPException(status_code=429, detail={"code": "budget_exceeded", "message": "cost budget exceeded"})


def _apply_charge(cost: float) -> None:
    budget_manager.spend(cost)


def _synthesize_answer(payload: GenerateRequest) -> tuple[str, list[str]]:
    answer = ""
    citations: list[str] = []
    chunks = payload.context.chunks if payload.context else []
    if chunks:
        top = chunks[:2]
        citations = [chunk.citation_key for chunk in top]
        summary = " ".join(chunk.content[:160].strip() for chunk in top)
        answer = f"제공된 근거를 기준으로 정리하면 {summary}"
        if payload.citations_required and citations:
            answer = f"{answer} [{' '.join(citations)}]"
    else:
        answer = "근거 문서가 충분하지 않아 확정 답변이 어렵습니다. 질문을 조금 더 구체적으로 입력해 주세요."
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


def _audit_event(trace_id: str, request_id: str, model: str, tokens: int, cost: float, status: str, reason: str | None) -> None:
    payload = {
        "trace_id": trace_id,
        "request_id": request_id,
        "provider": SETTINGS.provider,
        "model": model,
        "tokens": tokens,
        "cost_usd": cost,
        "status": status,
    }
    if reason:
        payload["reason_code"] = reason
    try:
        append_audit(SETTINGS.audit_log_path, payload)
    except Exception as exc:
        logger.warning("Failed to append LLM file audit log: %s", exc)
    try:
        append_audit_db(payload)
    except Exception as exc:
        logger.warning("Failed to append LLM DB audit log: %s", exc)


def _extract_citations_from_text(text: str) -> list[str]:
    matches = re.findall(r"\[([a-zA-Z0-9_\-:#]+)\]", text or "")
    seen = set()
    ordered: list[str] = []
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        ordered.append(match)
    return ordered


def _extract_json_payload(text: str | None) -> dict | None:
    if not isinstance(text, str):
        return None
    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = re.sub(r"^```(?:json)?", "", trimmed).strip()
        trimmed = re.sub(r"```$", "", trimmed).strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(trimmed[start : end + 1])
    except json.JSONDecodeError:
        return None


def _normalize_citations(raw: object, allowed: set[str]) -> list[str]:
    citations: list[str] = []
    if not allowed:
        return citations
    if isinstance(raw, list):
        for item in raw:
            key: str | None = None
            if isinstance(item, str):
                key = item
            elif isinstance(item, dict):
                for field in ("chunk_id", "citation_key", "doc_id", "id"):
                    value = item.get(field)
                    if isinstance(value, str) and value:
                        key = value
                        break
            if not key:
                continue
            if key not in allowed:
                continue
            if key not in citations:
                citations.append(key)
    return citations


def _allowed_citations(payload: GenerateRequest) -> set[str]:
    allowed: set[str] = set()
    if payload.context and payload.context.chunks:
        for chunk in payload.context.chunks:
            if chunk.citation_key:
                allowed.add(chunk.citation_key)
    return allowed


def _parse_answer(payload: GenerateRequest, content: str) -> tuple[str, list[str], str | None]:
    if not payload.citations_required:
        return content, [], None
    allowed = _allowed_citations(payload)
    parsed = _extract_json_payload(content)
    if parsed is None:
        extracted = _extract_citations_from_text(content)
        citations = _normalize_citations(extracted, allowed)
        return content, citations, "invalid_json"
    answer = parsed.get("answer")
    if not isinstance(answer, str):
        answer = content
    citations_raw = parsed.get("citations")
    citations = _normalize_citations(citations_raw, allowed)
    if not citations:
        extracted = _extract_citations_from_text(answer)
        citations = _normalize_citations(extracted, allowed)
    return answer, citations, None if citations else "missing_citations"


def _format_context(payload: GenerateRequest) -> str | None:
    if not payload.context or not payload.context.chunks:
        return None
    lines = ["Sources:"]
    for chunk in payload.context.chunks:
        key = chunk.citation_key
        if not key:
            continue
        snippet = (chunk.content or "").replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        details: list[str] = []
        if chunk.title:
            details.append(chunk.title)
        if chunk.url:
            details.append(chunk.url)
        prefix = " - ".join(details)
        if prefix:
            lines.append(f"[{key}] {prefix} :: {snippet}")
        else:
            lines.append(f"[{key}] {snippet}")
    return "\n".join(lines)


def _build_openai_messages(payload: GenerateRequest) -> list[dict]:
    messages: list[dict] = []
    if payload.citations_required:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Return ONLY valid JSON: "
                    '{"answer": string, "citations": ["citation_key", ...]}. '
                    "Use the provided sources only. "
                    "If insufficient evidence, answer with empty citations."
                ),
            }
        )
    context_block = _format_context(payload)
    if context_block:
        messages.append({"role": "system", "content": context_block})
    for msg in payload.messages:
        if msg.role and msg.content:
            messages.append({"role": msg.role, "content": msg.content})
    if not messages:
        messages.append({"role": "user", "content": ""})
    return messages


def _openai_url() -> str:
    return f"{SETTINGS.base_url}/chat/completions"


def _openai_headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if SETTINGS.api_key:
        headers["authorization"] = f"Bearer {SETTINGS.api_key}"
    return headers


def _openai_payload(payload: GenerateRequest, stream: bool) -> dict:
    body = {
        "model": payload.model or SETTINGS.default_model,
        "messages": _build_openai_messages(payload),
        "temperature": payload.temperature if payload.temperature is not None else SETTINGS.temperature,
        "stream": stream,
    }
    max_tokens = payload.max_tokens if payload.max_tokens is not None else SETTINGS.max_tokens
    if max_tokens:
        body["max_tokens"] = max_tokens
    return body


def _openai_extract_content(data: dict) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if content is not None:
                    return str(content)
            text = choice.get("text")
            if text is not None:
                return str(text)
    return ""


def _openai_extract_tokens(data: dict, answer: str) -> int:
    usage = data.get("usage") if isinstance(data, dict) else None
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int) and total > 0:
            return total
    return _estimate_tokens(answer)


async def _openai_generate(payload: GenerateRequest) -> tuple[str, list[str], int, str | None]:
    timeout = SETTINGS.timeout_ms / 1000.0
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(_openai_url(), json=_openai_payload(payload, stream=False), headers=_openai_headers())
        response.raise_for_status()
        data = response.json()
    content = _openai_extract_content(data if isinstance(data, dict) else {})
    answer, citations, reason = _parse_answer(payload, content)
    tokens = _openai_extract_tokens(data if isinstance(data, dict) else {}, answer)
    return answer, citations, tokens, reason


def _openai_stream(
    payload: GenerateRequest,
    resolved_trace: str,
    resolved_request: str,
    model: str,
) -> AsyncIterator[str]:
    async def generator() -> AsyncIterator[str]:
        yield _sse_event("meta", {"trace_id": resolved_trace, "request_id": resolved_request, "model": model})
        answer_parts: list[str] = []
        status = "ok"
        reason: str | None = None
        try:
            reserved_tokens = payload.max_tokens if payload.max_tokens is not None else SETTINGS.max_tokens
            reserved_cost = _charge_cost(reserved_tokens)
            _check_budget(reserved_cost)
            timeout = SETTINGS.timeout_ms / 1000.0
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    _openai_url(),
                    json=_openai_payload(payload, stream=True),
                    headers=_openai_headers(),
                ) as response:
                    response.raise_for_status()
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip() if raw_line else ""
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.split(":", 1)[1].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") if isinstance(event, dict) else None
                        if not isinstance(choices, list) or not choices:
                            continue
                        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                        content = None
                        if isinstance(delta, dict):
                            content = delta.get("content")
                        if content is None and isinstance(choices[0], dict):
                            content = choices[0].get("text")
                        if isinstance(content, str) and content:
                            answer_parts.append(content)
                            yield _sse_event("delta", {"delta": content})
            answer = "".join(answer_parts)
            parsed_answer, citations, reason = _parse_answer(payload, answer)
            if payload.citations_required and not citations:
                status = "fallback"
            tokens = _estimate_tokens(parsed_answer)
            cost = _charge_cost(tokens)
            _check_budget(cost)
            _apply_charge(cost)
            _audit_event(resolved_trace, resolved_request, model, tokens, cost, status, reason)
            yield _sse_event("done", {"status": status, "citations": citations})
        except HTTPException as exc:
            reason = "budget_exceeded"
            status = "error"
            tokens = _estimate_tokens("".join(answer_parts))
            cost = _charge_cost(tokens)
            _audit_event(resolved_trace, resolved_request, model, tokens, cost, status, reason)
            yield _sse_event("error", {"code": "budget_exceeded", "message": str(exc.detail)})
            yield _sse_event("done", {"status": "error", "citations": []})
        except Exception as exc:
            reason = "provider_error"
            status = "error"
            tokens = _estimate_tokens("".join(answer_parts))
            cost = _charge_cost(tokens)
            _audit_event(resolved_trace, resolved_request, model, tokens, cost, status, reason)
            yield _sse_event("error", {"code": "PROVIDER_TIMEOUT", "message": "LLM provider unavailable"})
            yield _sse_event("done", {"status": "error", "citations": []})

    return generator()


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

    should_stream = bool(stream or payload.stream)
    provider = SETTINGS.provider

    if provider == "openai_compat":
        if should_stream:
            return StreamingResponse(
                _openai_stream(payload, resolved_trace, resolved_request, model),
                media_type="text/event-stream",
                headers={"cache-control": "no-cache"},
            )
        try:
            answer, citations, tokens, reason = await _openai_generate(payload)
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail={"code": "timeout", "message": str(exc)}) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail={"code": "provider_error", "message": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"code": "provider_error", "message": str(exc)}) from exc

        cost = _charge_cost(tokens)
        _check_budget(cost)
        _apply_charge(cost)
        status = "ok"
        if payload.citations_required and not citations:
            status = "fallback"
        _audit_event(resolved_trace, resolved_request, model, tokens, cost, status, reason)
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

    answer, citations = _synthesize_answer(payload)
    tokens = _estimate_tokens(answer)
    cost = _charge_cost(tokens)
    _check_budget(cost)
    _apply_charge(cost)
    _audit_event(resolved_trace, resolved_request, model, tokens, cost, "ok", None)

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
