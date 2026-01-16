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

    tokens = tokenize(normalized)
    language = detect_language(normalized)

    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "client": body.get("client"),
        "user": body.get("user"),
        "query": {
            "raw": raw,
            "normalized": normalized,
            "canonical": normalized,
            "language": language,
            "tokens": tokens,
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
        "understanding": {
            "intent": "book_search",
            "entities": [],
            "filters": {},
        },
        "retrieval_hints": {
            "strategy": "bm25",
            "top_k": 200,
            "time_budget_ms": 350,
            "boost": {"title": 2.0, "author": 1.2},
        },
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
