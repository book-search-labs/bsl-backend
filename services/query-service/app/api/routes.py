import hashlib
import os
import re
import time
import unicodedata
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.lid import detect_language
from app.core.normalize import normalize_query, tokenize

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/query-context")
async def query_context(request: Request):
    trace_id, request_id = _extract_ids(request)
    body = await request.json()
    if not isinstance(body, dict):
        return _error_response(
            "invalid_request",
            "Request body must be a JSON object.",
            trace_id,
            request_id,
        )

    query = body.get("query")
    raw = query.get("raw") if isinstance(query, dict) else None
    if not isinstance(raw, str):
        return _error_response(
            "invalid_query",
            "Missing or invalid query.raw.",
            trace_id,
            request_id,
        )

    try:
        normalized = normalize_query(raw)
    except ValueError as exc:
        code = str(exc) if str(exc) else "invalid_query"
        message = "Query is empty after normalization." if code == "empty_query" else "Invalid query."
        return _error_response(code, message, trace_id, request_id)

    nfkc = unicodedata.normalize("NFKC", raw)
    nospace = normalized.replace(" ", "")
    final = normalized
    final_source = "norm"

    volume = _detect_volume(normalized)
    editions = _detect_editions(normalized)
    canonical_key = _build_canonical_key(final, volume, editions)

    tokens = _build_tokens(normalized)
    language = detect_language(normalized)

    tenant_id = os.getenv("BSL_TENANT_ID", "books")
    locale = os.getenv("BSL_LOCALE", "ko-KR")
    timezone = os.getenv("BSL_TIMEZONE", "Asia/Seoul")
    plan_id = "MVP_V1_1"

    response = {
        "meta": {
            "schemaVersion": "qc.v1.1",
            "traceId": trace_id,
            "requestId": request_id,
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
            "raw": raw,
            "nfkc": nfkc,
            "norm": normalized,
            "nospace": nospace,
            "final": final,
            "finalSource": final_source,
            "canonicalKey": canonical_key,
            "tokens": tokens,
            "protectedSpans": [],
            "normalized": {"rulesApplied": _rules_applied()},
        },
        "detected": _map_language(language),
        "slots": {
            "isbn": None,
            "volume": volume,
            "edition": editions,
            "set": {"value": False, "confidence": 1.0, "source": "mvp"},
            "chosung": {"value": False, "confidence": 1.0, "source": "mvp"},
        },
        "understanding": {
            "intent": "WORK_LOOKUP",
            "confidence": 0.5,
            "method": "mvp",
            "entities": {"title": [], "author": [], "publisher": [], "series": []},
            "constraints": {
                "preferredLogicalFields": ["title_ko", "series_ko", "author_ko"],
                "mustPreserve": [],
            },
        },
        "spell": {
            "applied": False,
            "original": raw,
            "corrected": normalized,
            "method": "none",
            "confidence": 1.0,
        },
        "rewrite": {
            "applied": False,
            "rewritten": normalized,
            "method": "none",
            "notes": "MVP",
        },
        "retrievalHints": _build_retrieval_hints(plan_id, canonical_key, tenant_id),
        "features": {},
        "policy": {},
        "executionTrace": {},
        "debug": {},
    }

    return response


def _extract_ids(request: Request) -> tuple[str, str]:
    trace_id = request.headers.get("x-trace-id")
    request_id = request.headers.get("x-request-id")
    if not trace_id:
        trace_id = f"trace_{uuid.uuid4().hex}"
    if not request_id:
        request_id = f"req_{uuid.uuid4().hex}"
    return trace_id, request_id


def _error_response(code: str, message: str, trace_id: str, request_id: str) -> JSONResponse:
    payload = {
        "error": {"code": code, "message": message},
        "trace_id": trace_id,
        "request_id": request_id,
    }
    return JSONResponse(status_code=400, content=payload)


def _build_tokens(normalized: str) -> list[dict]:
    tokens = []
    for idx, token in enumerate(tokenize(normalized)):
        tokens.append({"t": token, "pos": idx, "type": "term", "protected": False})
    return tokens


def _map_language(language: dict | None) -> dict:
    primary = "unknown"
    confidence = 0.0
    if isinstance(language, dict):
        primary = language.get("detected") or primary
        confidence = language.get("confidence", confidence)
    return {"lang": {"primary": primary, "confidence": confidence}, "isMixed": False}


def _detect_volume(normalized: str) -> int | None:
    match = re.search(r"(\d+)\s*권", normalized)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _detect_editions(normalized: str) -> list[str]:
    editions = []
    if "리커버" in normalized:
        editions.append("recover")
    return editions


def _build_canonical_key(final: str, volume: int | None, editions: list[str]) -> str:
    parts = [final]
    if volume is not None:
        parts.append(f"vol:{volume}")
    if editions:
        parts.append("edition:" + ",".join(editions))
    return "|".join(parts)


def _rules_applied() -> list[str]:
    return ["nfkc", "strip_control", "trim", "collapse_whitespace"]


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
