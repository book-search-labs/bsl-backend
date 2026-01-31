import hashlib
import os
import time
import uuid
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.analyzer import analyze_query
from app.core.cache import get_cache
from app.core.enhance import evaluate_gate, load_config
from app.core.metrics import metrics
from app.core.rewrite_log import get_rewrite_log, now_iso

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


@router.post("/query-context")
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

    response = _build_qc_v1_response(analysis, body, trace_id, request_id, span_id, cache_hit)
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
            response = _build_enhance_response(
                trace_id,
                request_id,
                decision=decision,
                strategy=cached.get("strategy", strategy),
                reason_codes=reason_codes,
                spell=cached.get("spell"),
                rewrite=cached.get("rewrite"),
                final=cached.get("final"),
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

    spell = _apply_spell(q_norm, strategy)
    rewrite = _apply_rewrite(spell["corrected"], strategy)
    final_text = rewrite["rewritten"] if rewrite["applied"] else spell["corrected"]
    final_source = "rewrite" if rewrite["applied"] else "spell"

    response = _build_enhance_response(
        trace_id,
        request_id,
        decision=decision,
        strategy=strategy,
        reason_codes=reason_codes,
        spell=spell,
        rewrite=rewrite,
        final={"text": final_text, "source": final_source},
        cache_flags={"enhance_hit": cache_hit, "deny_hit": False},
    )
    CACHE.set_json(
        enhance_cache_key,
        {
            "strategy": strategy,
            "spell": spell,
            "rewrite": rewrite,
            "final": {"text": final_text, "source": final_source},
        },
        ttl=_enhance_cache_ttl(),
    )
    _log_enhance(body, response, canonical_key)
    return JSONResponse(content=response, headers=_response_headers(trace_id, request_id, traceparent))


@router.get("/internal/qc/rewrite/failures")
async def rewrite_failures(request: Request):
    trace_id, request_id, _, traceparent = _extract_ids(request)
    params = request.query_params
    since = params.get("from")
    limit_raw = params.get("limit", "50")
    try:
        limit = max(1, min(int(limit_raw), 200))
    except ValueError:
        limit = 50
    items = get_rewrite_log().list_failures(since=since, limit=limit)
    canonical_key = analysis.get("canonical_key") or _hash_key(analysis.get("norm", ""))
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


def _prepare_analysis(raw: str, body: dict) -> tuple[dict[str, Any], bool]:
    locale = _resolve_locale(body)
    key = _norm_cache_key(raw, locale)
    cached = CACHE.get_json(key)
    if cached:
        metrics.inc("qs_norm_cache_hit_total")
        return cached, True
    analysis = analyze_query(raw, locale)
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
            "final": analysis.get("norm"),
            "finalSource": "norm",
            "canonicalKey": canonical_key,
            "tokens": _build_tokens(analysis.get("norm", "")),
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
                "title": [],
                "author": [],
                "publisher": [],
                "series": [series_hint] if series_hint else [],
            },
            "constraints": {
                "preferredLogicalFields": ["title_ko", "series_ko", "author_ko"],
                "mustPreserve": [],
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
        "retrievalHints": _build_retrieval_hints(plan_id, canonical_key, tenant_id),
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


def _apply_spell(text: str, strategy: str) -> dict:
    applied = strategy in {"SPELL_ONLY", "SPELL_THEN_REWRITE"}
    return {
        "applied": applied,
        "original": text,
        "corrected": text,
        "method": "noop" if applied else "none",
        "confidence": 1.0,
    }


def _apply_rewrite(text: str, strategy: str) -> dict:
    applied = strategy in {"REWRITE_ONLY", "SPELL_THEN_REWRITE", "RAG_REWRITE"}
    return {
        "applied": applied,
        "rewritten": text,
        "method": "noop" if applied else "none",
        "confidence": 0.6 if applied else 0.0,
        "notes": "MVP",
    }


def _build_enhance_response(
    trace_id: str,
    request_id: str,
    decision: str,
    strategy: str,
    reason_codes: list[str],
    spell: dict | None = None,
    rewrite: dict | None = None,
    final: dict | None = None,
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


def _log_enhance(body: dict, response: dict, canonical_key: str) -> None:
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
        final = response.get("final", {})
        if final and final.get("text") == body.get("q_norm"):
            failure_tag = "NO_IMPROVEMENT"
        metrics.inc("qs_rewrite_attempt_total", {"strategy": str(strategy)})

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
            "preferredLogicalFields": ["title_ko", "series_ko", "author_ko"],
        },
        "vector": {
            "enabled": True,
            "topKHint": 200,
            "embedModelHint": "bge-m3-v1",
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
            "allowedEmbedModels": ["bge-m3-v1"],
            "allowedRerankModels": ["toy_rerank_v1", "minilm-cross-v2"],
        },
    }


def _stable_cache_key(plan_id: str, canonical_key: str, tenant_id: str) -> str:
    raw = f"{plan_id}:{canonical_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"qc:{tenant_id}:{plan_id}:{digest}"
