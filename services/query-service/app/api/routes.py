import hashlib
import os
import time
import uuid
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.analyzer import analyze_query
from app.core.cache import get_cache
from app.core.enhance import evaluate_gate, load_config
from app.core.rag_candidates import retrieve_candidates
from app.core.rewrite import run_rewrite
from app.core.metrics import metrics
from app.core.rewrite_log import get_rewrite_log, now_iso
from app.core.spell import run_spell
from app.core.chat import (
    explain_chat_rag,
    get_chat_provider_snapshot,
    get_chat_session_state,
    reset_chat_session_state,
    run_chat,
    run_chat_stream,
)
from app.core.understanding import parse_understanding

router = APIRouter()
logger = logging.getLogger(__name__)

CACHE = get_cache()
ENHANCE_CONFIG = load_config()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics")
def metrics_endpoint():
    return metrics.snapshot()


@router.post("/query-context", deprecated=True)
async def query_context(request: Request):
    trace_id, request_id, span_id, traceparent = _extract_ids(request)
    body = await request.json()
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    raw = _extract_raw(body)
    if not isinstance(raw, str):
        return _error_response(
            "invalid_query",
            "Missing or invalid query.raw.",
            trace_id,
            request_id,
        )

    try:
        analysis, cache_hit = _prepare_analysis(raw, body)
    except ValueError as exc:
        code = str(exc) if str(exc) else "invalid_query"
        message = "Query is empty after normalization." if code == "empty_query" else "Invalid query."
        return _error_response(code, message, trace_id, request_id)

    response = _build_qc_v11_response(analysis, body, trace_id, request_id, span_id, cache_hit)
    _log_prepare(trace_id, request_id, analysis)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.post("/query/prepare")
async def query_prepare(request: Request):
    trace_id, request_id, span_id, traceparent = _extract_ids(request)
    body = await request.json()
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    raw = _extract_raw(body)
    if not isinstance(raw, str):
        return _error_response(
            "invalid_query",
            "Missing or invalid query.raw.",
            trace_id,
            request_id,
        )

    try:
        analysis, cache_hit = _prepare_analysis(raw, body)
    except ValueError as exc:
        code = str(exc) if str(exc) else "invalid_query"
        message = "Query is empty after normalization." if code == "empty_query" else "Invalid query."
        return _error_response(code, message, trace_id, request_id)

    response = _build_qc_v11_response(analysis, body, trace_id, request_id, span_id, cache_hit)
    _log_prepare(trace_id, request_id, analysis)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.post("/query/enhance")
async def query_enhance(request: Request):
    trace_id, request_id, span_id, traceparent = _extract_ids(request)
    body = await request.json()
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    if isinstance(body.get("trace_id"), str) and body.get("trace_id"):
        trace_id = body.get("trace_id")
    if isinstance(body.get("request_id"), str) and body.get("request_id"):
        request_id = body.get("request_id")

    q_norm = body.get("q_norm")
    q_nospace = body.get("q_nospace")
    reason = body.get("reason")
    detected = body.get("detected") or {}
    signals = body.get("signals") or {}
    locale = body.get("locale") or os.getenv("BSL_LOCALE", "ko-KR")

    if not isinstance(q_norm, str) or not isinstance(q_nospace, str):
        return _error_response(
            "invalid_query",
            "Missing or invalid q_norm/q_nospace.",
            trace_id,
            request_id,
        )

    canonical_key = body.get("canonical_key") or _hash_key(q_norm + locale)

    deny_cache_key = _enhance_deny_cache_key(q_norm, reason, locale)
    deny_hit = bool(reason and CACHE.get_json(deny_cache_key))
    if deny_hit:
        metrics.inc("qs_enhance_skipped_total", {"skip_reason": "deny_cache"})
        response = _build_enhance_response(
            trace_id,
            request_id,
            decision="SKIP",
            strategy="NONE",
            reason_codes=[reason, "DENY_CACHE_HIT"] if reason else ["DENY_CACHE_HIT"],
            cache_flags={"enhance_hit": False, "deny_hit": True},
        )
        _log_enhance(body, response, canonical_key)
        return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))

    gate = evaluate_gate(reason, signals, detected, canonical_key, CACHE, ENHANCE_CONFIG)
    decision = gate["decision"]
    strategy = gate["strategy"]
    reason_codes = gate["reason_codes"]

    enhance_cache_key = _enhance_cache_key(q_norm, reason, locale)
    cache_hit = False
    if decision == "RUN":
        cached = CACHE.get_json(enhance_cache_key)
        if cached:
            cache_hit = True
            metrics.inc("qs_enh_cache_hit_total")
            debug_payload = cached.get("debug") if _debug_enabled(body) else None
            response = _build_enhance_response(
                trace_id,
                request_id,
                decision=decision,
                strategy=cached.get("strategy", strategy),
                reason_codes=cached.get("reason_codes", reason_codes),
                spell=cached.get("spell"),
                rewrite=cached.get("rewrite"),
                final=cached.get("final"),
                hints=cached.get("hints"),
                rag=cached.get("rag"),
                debug=debug_payload,
                cache_flags={"enhance_hit": True, "deny_hit": False},
            )
            _log_enhance(body, response, canonical_key)
            return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))
        metrics.inc("qs_enh_cache_miss_total")

    if decision == "SKIP":
        response = _build_enhance_response(
            trace_id,
            request_id,
            decision=decision,
            strategy=strategy,
            reason_codes=reason_codes,
            cache_flags={"enhance_hit": False, "deny_hit": False},
        )
        if reason in {"ZERO_RESULTS", "LOW_CONFIDENCE", "HIGH_OOV"}:
            CACHE.set_json(deny_cache_key, {"skip": True}, ttl=_enhance_deny_ttl())
        _log_enhance(body, response, canonical_key)
        return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))

    spell, spell_meta = await _apply_spell(q_norm, strategy, trace_id, request_id, locale)
    rewrite, rewrite_meta, rag_info = await _apply_rewrite(
        spell.get("corrected", q_norm),
        strategy,
        trace_id,
        request_id,
        locale,
        reason,
    )
    reason_codes = _merge_reason_codes(reason_codes, spell_meta, rewrite_meta, rag_info)
    hints = _build_acceptance_hints(reason, strategy)

    final_text, final_source = _select_final(q_norm, spell, rewrite)

    debug_payload = _build_debug_payload(body, spell_meta, rewrite_meta, rag_info)
    response = _build_enhance_response(
        trace_id,
        request_id,
        decision=decision,
        strategy=strategy,
        reason_codes=reason_codes,
        spell=spell,
        rewrite=rewrite,
        final={"text": final_text, "source": final_source},
        hints=hints,
        rag=rag_info,
        debug=debug_payload,
        cache_flags={"enhance_hit": cache_hit, "deny_hit": False},
    )
    CACHE.set_json(
        enhance_cache_key,
        {
            "strategy": strategy,
            "reason_codes": reason_codes,
            "spell": spell,
            "rewrite": rewrite,
            "final": {"text": final_text, "source": final_source},
            "hints": hints,
            "rag": rag_info,
            "debug": debug_payload,
        },
        ttl=_enhance_cache_ttl(),
    )
    _log_enhance(body, response, canonical_key, spell_meta=spell_meta, rewrite_meta=rewrite_meta, rag_meta=rag_info)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.post("/chat")
async def chat(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    try:
        body = await request.json()
    except Exception:
        return _error_response(
            "invalid_request",
            "Request body must be a valid JSON object.",
            trace_id,
            request_id,
        )
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    if isinstance(body.get("trace_id"), str) and body.get("trace_id"):
        trace_id = body.get("trace_id")
    if isinstance(body.get("request_id"), str) and body.get("request_id"):
        request_id = body.get("request_id")

    _inject_chat_identity(body, request)

    options = body.get("options") if isinstance(body.get("options"), dict) else {}
    body_stream = bool(options.get("stream")) if isinstance(options.get("stream"), bool) else False
    query_stream = request.query_params.get("stream")
    should_stream = body_stream or str(query_stream).lower() in {"1", "true", "yes", "on"}
    if should_stream:
        headers = _response_headers(trace_id, request_id, traceparent)
        headers["cache-control"] = "no-cache"
        return StreamingResponse(
            run_chat_stream(body, trace_id, request_id),
            media_type="text/event-stream",
            headers=headers,
        )

    response = await run_chat(body, trace_id, request_id)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.post("/internal/rag/explain")
async def rag_explain(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    try:
        body = await request.json()
    except Exception:
        return _error_response(
            "invalid_request",
            "Request body must be a valid JSON object.",
            trace_id,
            request_id,
        )
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    if isinstance(body.get("trace_id"), str) and body.get("trace_id"):
        trace_id = body.get("trace_id")
    if isinstance(body.get("request_id"), str) and body.get("request_id"):
        request_id = body.get("request_id")

    response = await explain_chat_rag(body, trace_id, request_id)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.get("/internal/chat/providers")
async def chat_provider_snapshot(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "snapshot": get_chat_provider_snapshot(trace_id, request_id),
    }
    return JSONResponse(content=payload, headers=_response_headers(trace_id, request_id, traceparent))


@router.get("/internal/chat/session/state")
async def chat_session_state(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    session_id = str(request.query_params.get("session_id") or "").strip()
    if not session_id:
        metrics.inc("chat_session_state_requests_total", {"result": "missing_session_id"})
        return _error_response(
            "invalid_request",
            "Query parameter session_id is required.",
            trace_id,
            request_id,
        )
    try:
        snapshot = get_chat_session_state(session_id, trace_id, request_id)
    except ValueError:
        metrics.inc("chat_session_state_requests_total", {"result": "invalid_session_id"})
        return _error_response(
            "invalid_request",
            "Invalid session_id format.",
            trace_id,
            request_id,
        )
    metrics.inc(
        "chat_session_state_requests_total",
        {
            "result": "ok",
            "has_unresolved": "true" if isinstance(snapshot.get("unresolved_context"), dict) else "false",
        },
    )
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "session": {
            "session_id": snapshot["session_id"],
            "fallback_count": snapshot["fallback_count"],
            "fallback_escalation_threshold": snapshot["fallback_escalation_threshold"],
            "escalation_ready": snapshot["escalation_ready"],
            "recommended_action": snapshot["recommended_action"],
            "recommended_message": snapshot["recommended_message"],
            "unresolved_context": snapshot["unresolved_context"],
        },
    }
    return JSONResponse(content=payload, headers=_response_headers(trace_id, request_id, traceparent))


@router.post("/internal/chat/session/reset")
async def chat_session_reset(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    try:
        body = await request.json()
    except Exception:
        metrics.inc("chat_session_reset_requests_total", {"result": "invalid_json"})
        return _error_response(
            "invalid_request",
            "Request body must be a valid JSON object.",
            trace_id,
            request_id,
        )
    if not isinstance(body, dict):
        metrics.inc("chat_session_reset_requests_total", {"result": "invalid_body"})
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    if isinstance(body.get("trace_id"), str) and body.get("trace_id"):
        trace_id = body.get("trace_id")
    if isinstance(body.get("request_id"), str) and body.get("request_id"):
        request_id = body.get("request_id")

    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        metrics.inc("chat_session_reset_requests_total", {"result": "missing_session_id"})
        return _error_response(
            "invalid_request",
            "Field session_id is required.",
            trace_id,
            request_id,
        )
    try:
        snapshot = reset_chat_session_state(session_id, trace_id, request_id)
    except ValueError:
        metrics.inc("chat_session_reset_requests_total", {"result": "invalid_session_id"})
        return _error_response(
            "invalid_request",
            "Invalid session_id format.",
            trace_id,
            request_id,
        )
    metrics.inc(
        "chat_session_reset_requests_total",
        {
            "result": "ok",
            "had_unresolved": "true" if bool(snapshot.get("previous_unresolved_context")) else "false",
        },
    )
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "session": {
            "session_id": snapshot["session_id"],
            "reset_applied": snapshot["reset_applied"],
            "previous_fallback_count": snapshot["previous_fallback_count"],
            "previous_unresolved_context": snapshot["previous_unresolved_context"],
            "reset_at_ms": snapshot["reset_at_ms"],
        },
    }
    return JSONResponse(content=payload, headers=_response_headers(trace_id, request_id, traceparent))


@router.get("/internal/qc/rewrite/failures")
async def rewrite_failures(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    params = request.query_params
    since = params.get("since") or params.get("from")
    reason = params.get("reason")
    limit_raw = params.get("limit", "50")
    try:
        limit = max(1, min(int(limit_raw), 500))
    except ValueError:
        limit = 50
    try:
        items = get_rewrite_log().list_failures(since=since, limit=limit, reason=reason)
    except Exception as exc:
        logger.warning("rewrite failure list failed: %s", exc)
        items = []
    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "items": items,
    }
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


def _extract_raw(body: dict) -> str | None:
    if "query" in body and isinstance(body.get("query"), dict):
        return body["query"].get("raw")
    if "raw" in body:
        return body.get("raw")
    return None


def _extract_ids(request: Request) -> tuple[str, str, str | None, str | None]:
    trace_id = request.headers.get("x-trace-id")
    request_id = request.headers.get("x-request-id")
    traceparent = request.headers.get("traceparent")
    span_id = None

    if not trace_id and traceparent:
        parsed_trace, parsed_span = _parse_traceparent(traceparent)
        trace_id = parsed_trace or trace_id
        span_id = parsed_span

    if not trace_id:
        trace_id = f"trace_{uuid.uuid4().hex}"
    if not request_id:
        request_id = f"req_{uuid.uuid4().hex}"
    return trace_id, request_id, span_id, traceparent


def _parse_traceparent(value: str) -> tuple[str | None, str | None]:
    parts = value.split("-")
    if len(parts) != 4:
        return None, None
    trace_id = parts[1]
    span_id = parts[2]
    if len(trace_id) != 32 or len(span_id) != 16:
        return None, None
    return trace_id, span_id


def _error_response(code: str, message: str, trace_id: str, request_id: str) -> JSONResponse:
    payload = {
        "error": {"code": code, "message": message},
        "trace_id": trace_id,
        "request_id": request_id,
    }
    return JSONResponse(status_code=400, content=payload)


def _response_headers(trace_id: str, request_id: str, traceparent: str | None) -> dict[str, str]:
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    if traceparent:
        headers["traceparent"] = traceparent
    return headers


def _inject_chat_identity(body: dict, request: Request) -> None:
    if not isinstance(body, dict):
        return
    client = body.get("client")
    if not isinstance(client, dict):
        client = {}
        body["client"] = client

    user_id = request.headers.get("x-user-id")
    if isinstance(user_id, str) and user_id.strip():
        client["user_id"] = user_id.strip()
    admin_id = request.headers.get("x-admin-id")
    if isinstance(admin_id, str) and admin_id.strip():
        client["admin_id"] = admin_id.strip()


def _prepare_analysis(raw: str, body: dict) -> tuple[dict[str, Any], bool]:
    locale = _resolve_locale(body)
    key = _norm_cache_key(raw, locale)
    cached = CACHE.get_json(key)
    if cached:
        metrics.inc("qs_norm_cache_hit_total")
        return cached, True
    analysis = analyze_query(raw, locale)
    understanding = parse_understanding(analysis.get("norm") or "")
    analysis["understanding"] = understanding
    analysis["preferred_fields"] = understanding.get("preferred_fields", [])
    analysis["explicit_filters"] = understanding.get("filters", [])
    analysis["residual_text"] = understanding.get("residual_text", "")
    analysis["has_explicit"] = understanding.get("has_explicit", False)
    CACHE.set_json(key, analysis, ttl=_norm_cache_ttl())
    metrics.inc("qs_norm_cache_miss_total")
    return analysis, False


def _resolve_locale(body: dict) -> str:
    locale = None
    client = body.get("client") if isinstance(body.get("client"), dict) else None
    if client:
        locale = client.get("locale")
    return locale or os.getenv("BSL_LOCALE", "ko-KR")


def _norm_cache_key(raw: str, locale: str) -> str:
    version = os.getenv("QS_NORM_CACHE_VERSION", "v1")
    digest = hashlib.sha256(f"{raw}|{locale}|{version}".encode("utf-8")).hexdigest()[:16]
    return f"qs:norm:{version}:{digest}"


def _enhance_cache_key(q_norm: str, reason: str | None, locale: str) -> str:
    version = os.getenv("QS_ENH_CACHE_VERSION", "v1")
    base = f"{q_norm}|{reason}|{locale}|{version}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"qs:enh:{version}:{digest}"


def _enhance_deny_cache_key(q_norm: str, reason: str | None, locale: str) -> str:
    version = os.getenv("QS_ENH_DENY_CACHE_VERSION", "v1")
    base = f"{q_norm}|{reason}|{locale}|{version}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"qs:enh:deny:{version}:{digest}"


def _norm_cache_ttl() -> int:
    return int(os.getenv("QS_NORM_CACHE_TTL_SEC", "3600"))


def _enhance_cache_ttl() -> int:
    return int(os.getenv("QS_ENH_CACHE_TTL_SEC", "900"))


def _enhance_deny_ttl() -> int:
    return int(os.getenv("QS_ENH_DENY_CACHE_TTL_SEC", "120"))


def _hash_key(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"ck:{digest}"


def _build_qc_v11_response(
    analysis: dict[str, Any],
    body: dict,
    trace_id: str,
    request_id: str,
    span_id: str | None,
    cache_hit: bool,
) -> dict:
    tenant_id = os.getenv("BSL_TENANT_ID", "books")
    locale = _resolve_locale(body)
    timezone = os.getenv("BSL_TIMEZONE", "Asia/Seoul")
    plan_id = "MVP_V1_1"

    volume = analysis.get("volume")
    isbn = analysis.get("isbn")
    series_hint = analysis.get("series")
    canonical_key = analysis.get("canonical_key") or _hash_key(analysis.get("norm", ""))
    understanding_info = analysis.get("understanding") or {}
    entities = understanding_info.get("entities") or {}
    preferred_fields = analysis.get("preferred_fields") or []
    explicit_filters = analysis.get("explicit_filters") or []
    residual_text = analysis.get("residual_text") or ""
    has_explicit = bool(analysis.get("has_explicit"))

    author_entities = list(entities.get("author") or [])
    title_entities = list(entities.get("title") or [])
    publisher_entities = list(entities.get("publisher") or [])
    series_entities = list(entities.get("series") or [])
    isbn_entities = list(entities.get("isbn") or [])

    if series_hint and series_hint not in series_entities:
        series_entities.append(series_hint)

    default_preferred = ["title_ko", "title_ko.edge", "series_ko", "author_ko"]
    if not preferred_fields:
        preferred_fields = default_preferred

    final_text, final_source = _resolve_final_text(
        analysis.get("norm", ""),
        residual_text,
        author_entities,
        title_entities,
        publisher_entities,
        series_entities,
        isbn_entities,
        has_explicit,
    )
    retrieval_hints = _build_retrieval_hints(plan_id, canonical_key, tenant_id)
    if preferred_fields:
        retrieval_hints["lexical"]["preferredLogicalFields"] = preferred_fields
    if explicit_filters:
        retrieval_hints["filters"] = explicit_filters
    if isbn_entities and not residual_text:
        retrieval_hints["vector"]["enabled"] = False
        retrieval_hints["rerank"]["enabled"] = False

    response = {
        "meta": {
            "schemaVersion": "qc.v1.1",
            "traceId": trace_id,
            "requestId": request_id,
            "spanId": span_id,
            "timestampMs": int(time.time() * 1000),
            "tenantId": tenant_id,
            "locale": locale,
            "timezone": timezone,
            "client": body.get("client"),
            "user": body.get("user"),
            "compat": {
                "minSearchRequestVersion": "sr.v1.0",
                "minRerankRequestVersion": "rr.v1.0",
            },
        },
        "query": {
            "raw": analysis.get("raw"),
            "nfkc": analysis.get("nfkc"),
            "norm": analysis.get("norm"),
            "nospace": analysis.get("nospace"),
            "final": final_text,
            "finalSource": final_source,
            "canonicalKey": canonical_key,
            "tokens": _build_tokens(final_text),
            "protectedSpans": [],
            "normalized": {"rulesApplied": analysis.get("rules", [])},
        },
        "detected": {
            "mode": analysis.get("mode"),
            "isIsbn": bool(isbn),
            "hasVolume": volume is not None,
            "lang": {
                "primary": analysis.get("lang"),
                "confidence": analysis.get("lang_confidence", 0.0),
            },
            "isMixed": analysis.get("is_mixed", False),
        },
        "slots": {
            "isbn": isbn,
            "volume": volume,
            "edition": _detect_editions(analysis.get("norm", "")),
            "set": {"value": bool(series_hint), "confidence": 0.7 if series_hint else 0.3, "source": "rule"},
            "chosung": {"value": analysis.get("is_chosung", False), "confidence": 0.8, "source": "rule"},
        },
        "understanding": {
            "intent": "WORK_LOOKUP",
            "confidence": 0.5,
            "method": "mvp",
            "entities": {
                "title": title_entities,
                "author": author_entities,
                "publisher": publisher_entities,
                "series": series_entities,
                "isbn": isbn_entities,
            },
            "constraints": {
                "preferredLogicalFields": preferred_fields,
                "mustPreserve": [],
                "residualText": residual_text,
            },
        },
        "spell": {
            "applied": False,
            "original": analysis.get("raw"),
            "corrected": analysis.get("norm"),
            "method": "none",
            "confidence": 1.0,
        },
        "rewrite": {
            "applied": False,
            "rewritten": analysis.get("norm"),
            "method": "none",
            "notes": "MVP",
        },
        "retrievalHints": retrieval_hints,
        "features": {},
        "policy": {},
        "executionTrace": {},
        "debug": {
            "cache": {"norm_hit": cache_hit},
        },
    }
    return response


def _build_qc_v1_response(
    analysis: dict[str, Any],
    body: dict,
    trace_id: str,
    request_id: str,
    span_id: str | None,
    cache_hit: bool,
) -> dict:
    locale = _resolve_locale(body)
    canonical_key = analysis.get("canonical_key") or _hash_key(analysis.get("norm", ""))
    detected = {
        "mode": analysis.get("mode"),
        "is_isbn": bool(analysis.get("isbn")),
        "has_volume": analysis.get("volume") is not None,
        "lang": analysis.get("lang"),
        "volume": analysis.get("volume"),
        "isbn": analysis.get("isbn"),
        "is_mixed": analysis.get("is_mixed", False),
    }
    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "span_id": span_id,
        "q_raw": analysis.get("raw"),
        "q_nfkc": analysis.get("nfkc"),
        "q_norm": analysis.get("norm"),
        "q_nospace": analysis.get("nospace"),
        "canonical_key": canonical_key,
        "locale": locale,
        "client": body.get("client"),
        "user": body.get("user"),
        "detected": detected,
        "hints": {
            "intent_hint": "WORK_LOOKUP",
            "budget": {"low_latency_mode": False},
        },
        "confidence": analysis.get("confidence", {}),
        "expanded": {"aliases": [], "series": [analysis.get("series")] if analysis.get("series") else [], "author_variants": []},
    }
    return response


def _resolve_final_text(
    norm: str,
    residual_text: str,
    author_entities: list[str],
    title_entities: list[str],
    publisher_entities: list[str],
    series_entities: list[str],
    isbn_entities: list[str],
    has_explicit: bool,
) -> tuple[str, str]:
    if residual_text:
        return residual_text, "explicit_residual"
    if has_explicit:
        parts: list[str] = []
        parts.extend(title_entities)
        parts.extend(author_entities)
        parts.extend(series_entities)
        parts.extend(publisher_entities)
        parts.extend(isbn_entities)
        composed = " ".join([part for part in parts if part])
        if composed:
            return composed, "explicit_entities"
    return norm, "norm"


async def _apply_spell(
    text: str,
    strategy: str,
    trace_id: str,
    request_id: str,
    locale: str,
) -> tuple[dict, dict]:
    if strategy not in {"SPELL_ONLY", "SPELL_THEN_REWRITE"}:
        return (
            {
                "applied": False,
                "original": text,
                "corrected": text,
                "method": "none",
                "confidence": 0.0,
            },
            {"provider": "none", "error_code": None, "error_message": None, "reject_reason": None},
        )
    return await run_spell(text, trace_id, request_id, locale)


async def _apply_rewrite(
    text: str,
    strategy: str,
    trace_id: str,
    request_id: str,
    locale: str,
    reason: str | None,
) -> tuple[dict, dict, dict | None]:
    if strategy not in {"REWRITE_ONLY", "SPELL_THEN_REWRITE", "RAG_REWRITE"}:
        return (
            {
                "applied": False,
                "rewritten": text,
                "method": "none",
                "confidence": 0.0,
                "notes": "skipped",
            },
            {"provider": "none", "error_code": None, "error_message": None, "reject_reason": None},
            None,
        )

    candidates = None
    rag_info = None
    if strategy == "RAG_REWRITE":
        metrics.inc("qs_rag_rewrite_attempt_total")
        candidates = await retrieve_candidates(text, trace_id, request_id)
        rag_info = {
            "candidate_count": len(candidates),
            "source": "opensearch",
            "degraded": False,
        }
        if candidates:
            metrics.inc("qs_rag_rewrite_hit_total")
        else:
            metrics.inc("qs_rag_rewrite_miss_total")
            rag_info["degraded"] = True
            rag_info["reason_code"] = "RAG_NO_CANDIDATES"
            fallback = os.getenv("QS_RAG_REWRITE_FALLBACK", "rewrite_only").lower()
            if fallback not in {"rewrite_only", "rewrite"}:
                metrics.inc("qs_rag_rewrite_degrade_total", {"mode": "skip"})
                return (
                    {
                        "applied": False,
                        "rewritten": text,
                        "method": "rag_skip",
                        "confidence": 0.0,
                        "notes": "rag_no_candidates",
                    },
                    {"provider": "rag", "error_code": None, "error_message": None, "reject_reason": "rag_no_candidates"},
                    rag_info,
                )
            metrics.inc("qs_rag_rewrite_degrade_total", {"mode": "rewrite_only"})
            candidates = None

    rewrite_payload, rewrite_meta = await run_rewrite(text, trace_id, request_id, reason, locale, candidates=candidates)
    return rewrite_payload, rewrite_meta, rag_info


def _merge_reason_codes(
    reason_codes: list[str],
    spell_meta: dict | None,
    rewrite_meta: dict | None,
    rag_info: dict | None,
) -> list[str]:
    merged = list(reason_codes)

    def _append(code: str | None) -> None:
        if code and code not in merged:
            merged.append(code)

    if spell_meta:
        error_code = spell_meta.get("error_code")
        reject_reason = spell_meta.get("reject_reason")
        if error_code:
            _append(f"SPELL_ERROR_{str(error_code).upper()}")
        if reject_reason:
            _append(f"SPELL_REJECT_{str(reject_reason).upper()}")

    if rewrite_meta:
        error_code = rewrite_meta.get("error_code")
        reject_reason = rewrite_meta.get("reject_reason")
        if error_code:
            _append(f"REWRITE_ERROR_{str(error_code).upper()}")
        if reject_reason:
            _append(f"REWRITE_REJECT_{str(reject_reason).upper()}")

    if rag_info and rag_info.get("reason_code"):
        _append(str(rag_info.get("reason_code")))

    return merged


def _select_final(q_norm: str, spell: dict, rewrite: dict) -> tuple[str, str]:
    if rewrite and rewrite.get("applied"):
        return rewrite.get("rewritten", q_norm), "rewrite"
    if spell and spell.get("applied"):
        return spell.get("corrected", q_norm), "spell"
    return q_norm, "original"


def _build_acceptance_hints(reason: str | None, strategy: str) -> dict | None:
    if strategy not in {"REWRITE_ONLY", "SPELL_THEN_REWRITE", "RAG_REWRITE"}:
        return None
    if not reason:
        return None
    recommended = []
    if reason == "ZERO_RESULTS":
        recommended = ["results_improve"]
    elif reason == "LOW_CONFIDENCE":
        recommended = ["score_gap_improve", "results_improve"]
    elif reason == "HIGH_OOV":
        recommended = ["results_improve"]
    elif reason == "USER_EXPLICIT":
        recommended = ["user_override"]
    return {
        "acceptance": {
            "reason": reason,
            "recommended_accept_if": recommended,
        }
    }


def _debug_enabled(body: dict) -> bool:
    if isinstance(body.get("debug"), bool):
        return body.get("debug")
    return os.getenv("QS_ENHANCE_DEBUG", "false").lower() in {"1", "true", "yes"}


def _build_debug_payload(
    body: dict,
    spell_meta: dict | None,
    rewrite_meta: dict | None,
    rag_meta: dict | None,
) -> dict | None:
    if not _debug_enabled(body):
        return None
    debug: dict[str, Any] = {}
    if spell_meta:
        spell_debug = {
            "provider": spell_meta.get("provider"),
            "candidate_mode": spell_meta.get("candidate_mode"),
            "candidate_input": spell_meta.get("candidate_input"),
            "candidates": spell_meta.get("candidates"),
            "provider_latency_ms": spell_meta.get("provider_latency_ms"),
            "provider_model": spell_meta.get("provider_model"),
            "error_code": spell_meta.get("error_code"),
            "reject_reason": spell_meta.get("reject_reason"),
        }
        debug["spell"] = {k: v for k, v in spell_debug.items() if v is not None}
    if rewrite_meta:
        rewrite_debug = {
            "provider": rewrite_meta.get("provider"),
            "error_code": rewrite_meta.get("error_code"),
            "reject_reason": rewrite_meta.get("reject_reason"),
        }
        debug["rewrite"] = {k: v for k, v in rewrite_debug.items() if v is not None}
    if rag_meta:
        debug["rag"] = rag_meta
    return debug or None


def _build_enhance_response(
    trace_id: str,
    request_id: str,
    decision: str,
    strategy: str,
    reason_codes: list[str],
    spell: dict | None = None,
    rewrite: dict | None = None,
    final: dict | None = None,
    hints: dict | None = None,
    rag: dict | None = None,
    debug: dict | None = None,
    cache_flags: dict | None = None,
) -> dict:
    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "decision": decision,
        "strategy": strategy,
        "reason_codes": reason_codes,
        "cache": cache_flags or {"enhance_hit": False, "deny_hit": False},
    }
    if spell:
        response["spell"] = spell
    if rewrite:
        response["rewrite"] = rewrite
    if final:
        response["final"] = final
    if hints:
        response["hints"] = hints
    if rag:
        response["rag"] = rag
    if debug:
        response["debug"] = debug
    return response


def _log_prepare(trace_id: str, request_id: str, analysis: dict[str, Any]) -> None:
    q_hash = hashlib.sha256((analysis.get("norm") or "").encode("utf-8")).hexdigest()[:12]
    logger.info(
        "qs_prepare trace_id=%s request_id=%s q_hash=%s mode=%s",
        trace_id,
        request_id,
        q_hash,
        analysis.get("mode"),
    )


def _log_enhance(
    body: dict,
    response: dict,
    canonical_key: str,
    spell_meta: dict | None = None,
    rewrite_meta: dict | None = None,
    rag_meta: dict | None = None,
) -> None:
    decision = response.get("decision")
    strategy = response.get("strategy")
    reason_codes = response.get("reason_codes", [])
    metrics.inc("qs_enhance_requests_total", {"decision": str(decision), "strategy": str(strategy)})

    failure_tag = None
    if decision == "SKIP":
        if "COOLDOWN_HIT" in reason_codes:
            failure_tag = "COOLDOWN_SKIP"
        elif "BUDGET_EXCEEDED" in reason_codes:
            failure_tag = "BUDGET_SKIP"
        elif "LOW_BUDGET" in reason_codes:
            failure_tag = "LOW_BUDGET_SKIP"
        elif "ISBN_QUERY" in reason_codes:
            failure_tag = "ISBN_SKIP"
        else:
            failure_tag = "POLICY_SKIP"
        metrics.inc("qs_enhance_skipped_total", {"skip_reason": failure_tag})
    elif decision == "RUN":
        if rewrite_meta:
            error_code = rewrite_meta.get("error_code")
            reject_reason = rewrite_meta.get("reject_reason")
            if error_code:
                failure_tag = f"REWRITE_ERROR_{str(error_code).upper()}"
            elif reject_reason:
                failure_tag = f"REWRITE_REJECT_{str(reject_reason).upper()}"
        if failure_tag is None and spell_meta:
            error_code = spell_meta.get("error_code")
            reject_reason = spell_meta.get("reject_reason")
            if error_code:
                failure_tag = f"SPELL_ERROR_{str(error_code).upper()}"
            elif reject_reason:
                failure_tag = f"SPELL_REJECT_{str(reject_reason).upper()}"
        if failure_tag is None and rag_meta and rag_meta.get("reason_code"):
            failure_tag = str(rag_meta.get("reason_code"))
        if failure_tag is None:
            final = response.get("final", {})
            if final and final.get("text") == body.get("q_norm"):
                failure_tag = "NO_IMPROVEMENT"

    log_entry = {
        "request_id": body.get("request_id") or response.get("request_id"),
        "trace_id": body.get("trace_id") or response.get("trace_id"),
        "canonical_key": canonical_key,
        "q_raw": body.get("q_raw") or body.get("q_norm"),
        "q_norm": body.get("q_norm"),
        "reason": body.get("reason"),
        "decision": decision,
        "strategy": strategy,
        "spell": response.get("spell"),
        "rewrite": response.get("rewrite"),
        "final": response.get("final"),
        "before": body.get("signals"),
        "after": body.get("after"),
        "accepted": body.get("accepted"),
        "failure_tag": failure_tag,
        "error_code": (rewrite_meta or {}).get("error_code") or (spell_meta or {}).get("error_code"),
        "error_message": (rewrite_meta or {}).get("error_message") or (spell_meta or {}).get("error_message"),
        "replay_payload": {
            "q_norm": body.get("q_norm"),
            "q_nospace": body.get("q_nospace"),
            "reason": body.get("reason"),
            "signals": body.get("signals"),
            "detected": body.get("detected"),
        },
        "created_at": now_iso(),
    }
    get_rewrite_log().log(log_entry)

    if failure_tag:
        metrics.inc("qs_rewrite_failure_total", {"failure_tag": failure_tag})
    if decision == "RUN" and failure_tag is None:
        metrics.inc("qs_rewrite_accept_total")

    logger.info(
        "qs_enhance decision=%s strategy=%s reason_codes=%s canonical_key=%s",
        decision,
        strategy,
        reason_codes,
        canonical_key,
    )


def _build_tokens(normalized: str) -> list[dict]:
    tokens = []
    for idx, token in enumerate(normalized.split(" ")):
        if not token:
            continue
        tokens.append({"t": token, "pos": idx, "type": "term", "protected": False})
    return tokens


def _detect_editions(normalized: str) -> list[str]:
    editions = []
    if "리커버" in normalized:
        editions.append("recover")
    if "개정판" in normalized:
        editions.append("revised")
    if "특별판" in normalized:
        editions.append("special")
    return editions


def _build_retrieval_hints(plan_id: str, canonical_key: str, tenant_id: str) -> dict:
    cache_key = _stable_cache_key(plan_id, canonical_key, tenant_id)
    return {
        "planId": plan_id,
        "queryTextSource": "query.final",
        "lexical": {
            "enabled": True,
            "operator": "and",
            "topKHint": 300,
            "analyzerHint": "ko_search",
            "minimumShouldMatch": "2<75%",
            "preferredLogicalFields": ["title_ko", "title_ko.edge", "series_ko", "author_ko"],
        },
        "vector": {
            "enabled": True,
            "topKHint": 200,
            "embedModelHint": "bge-m3",
            "fusionHint": {
                "method": "rrf",
                "k": 60,
                "weightHint": {"lexical": 0.6, "vector": 0.4},
            },
        },
        "rerank": {
            "enabled": False,
            "topKHint": 50,
            "rerankModelHint": "toy_rerank_v1",
            "featureHints": {"useVolumeSignal": True, "useEditionSignal": True},
        },
        "filters": [],
        "fallbackPolicy": [
            {
                "id": "FB1_LEXICAL_ONLY",
                "when": {"onTimeout": True, "onVectorError": True},
                "mutations": {
                    "disable": ["vector", "rerank"],
                    "useQueryTextSource": "query.norm",
                },
            },
            {
                "id": "FB2_NO_RERANK",
                "when": {"onRerankTimeout": True, "onRerankError": True},
                "mutations": {
                    "disable": ["rerank"],
                    "useQueryTextSource": "query.final",
                },
            },
        ],
        "executionHint": {
            "timeoutMs": 120,
            "budgetMs": {"lexical": 45, "vector": 45, "rerank": 25, "overhead": 5},
            "concurrencyHint": {"maxFanout": 2, "strategy": "parallel_lex_vec"},
            "cacheHint": {"enabled": True, "cacheKey": cache_key, "ttlSec": 120},
        },
        "guardrails": {
            "maxLexicalTopK": 1000,
            "maxVectorTopK": 500,
            "maxRerankTopK": 200,
            "allowedFusionMethods": ["rrf", "weighted_sum"],
            "allowedEmbedModels": ["bge-m3"],
            "allowedRerankModels": ["toy_rerank_v1", "minilm-cross-v2"],
        },
    }


def _stable_cache_key(plan_id: str, canonical_key: str, tenant_id: str) -> str:
    raw = f"{plan_id}:{canonical_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"qc:{tenant_id}:{plan_id}:{digest}"
