import hashlib
import json
import os
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.analyzer import analyze_query
from app.core.cache import get_cache
from app.core.metrics import metrics
from app.core.chat_tools import run_tool_chat
from app.core.rag import retrieve_chunks_with_trace
from app.core.rag_candidates import retrieve_candidates
from app.core.rewrite import run_rewrite

_CACHE = get_cache()


def _llm_url() -> str:
    return os.getenv("QS_LLM_URL", "http://localhost:8010").rstrip("/")


def _llm_model() -> str:
    return os.getenv("QS_LLM_MODEL", "toy-rag-v1")


def _llm_timeout_sec() -> float:
    return float(os.getenv("QS_LLM_TIMEOUT_SEC", "10.0"))


def _llm_stream_enabled() -> bool:
    return str(os.getenv("QS_LLM_STREAM_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _rewrite_on_bad_enabled() -> bool:
    return str(os.getenv("QS_CHAT_REWRITE_ON_BAD", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _retrieval_cache_ttl_sec() -> int:
    return int(os.getenv("QS_RAG_RETRIEVAL_CACHE_TTL_SEC", "180"))


def _answer_cache_ttl_sec() -> int:
    return int(os.getenv("QS_RAG_ANSWER_CACHE_TTL_SEC", "120"))


def _answer_cache_enabled() -> bool:
    return str(os.getenv("QS_RAG_ANSWER_CACHE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _bad_score_threshold() -> float:
    return float(os.getenv("QS_RAG_BAD_SCORE_THRESHOLD", "0.03"))


def _min_diversity_ratio() -> float:
    return float(os.getenv("QS_RAG_MIN_DIVERSITY_RATIO", "0.4"))


def _prompt_version() -> str:
    return os.getenv("QS_CHAT_PROMPT_VERSION", "v1")


def _output_guard_enabled() -> bool:
    return str(os.getenv("QS_CHAT_OUTPUT_GUARD_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _guard_high_risk_min_citations() -> int:
    return max(1, int(os.getenv("QS_CHAT_GUARD_HIGH_RISK_MIN_CITATIONS", "1")))


def _risk_band_high_keywords() -> List[str]:
    raw = os.getenv(
        "QS_CHAT_RISK_HIGH_KEYWORDS",
        "주문,결제,환불,취소,배송,주소,payment,refund,cancel,shipping,address",
    )
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _guard_forbidden_answer_keywords() -> List[str]:
    raw = os.getenv(
        "QS_CHAT_GUARD_FORBIDDEN_ANSWER_KEYWORDS",
        "무조건,반드시,절대,100% 보장,guarantee,always",
    )
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _chat_min_citation_coverage_ratio() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_MIN_CITATION_COVERAGE_RATIO", "0.2"))))


def _chat_high_risk_min_citation_coverage_ratio() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_HIGH_RISK_MIN_CITATION_COVERAGE_RATIO", "0.5"))))


def _chat_max_message_chars() -> int:
    return max(100, int(os.getenv("QS_CHAT_MAX_MESSAGE_CHARS", "1200")))


def _chat_max_history_turns() -> int:
    return max(1, int(os.getenv("QS_CHAT_MAX_HISTORY_TURNS", "12")))


def _chat_max_total_chars() -> int:
    return max(_chat_max_message_chars(), int(os.getenv("QS_CHAT_MAX_TOTAL_CHARS", "6000")))


def _chat_max_top_k() -> int:
    return max(1, int(os.getenv("QS_CHAT_MAX_TOP_K", "20")))


def _chat_session_id_max_len() -> int:
    return max(16, int(os.getenv("QS_CHAT_SESSION_ID_MAX_LEN", "64")))


def _chat_session_id_pattern() -> re.Pattern[str]:
    return re.compile(os.getenv("QS_CHAT_SESSION_ID_PATTERN", r"^[A-Za-z0-9:_-]+$"))


def _unresolved_context_ttl_sec() -> int:
    return max(300, int(os.getenv("QS_CHAT_UNRESOLVED_CONTEXT_TTL_SEC", "1800")))


def _extract_citations_from_text(text: str) -> List[str]:
    matches = re.findall(r"\[([a-zA-Z0-9_\-:#]+)\]", text or "")
    seen: set[str] = set()
    ordered: List[str] = []
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        ordered.append(match)
    return ordered


def _normalize_query(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _canonical_key(query: str, locale: str) -> str:
    try:
        return analyze_query(query, locale).get("canonical_key") or f"ck:{_hash_text(_normalize_query(query))}"
    except Exception:
        return f"ck:{_hash_text(_normalize_query(query))}"


def _locale_from_request(request: Dict[str, Any]) -> str:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    locale = client.get("locale") if isinstance(client, dict) else None
    if isinstance(locale, str) and locale.strip():
        return locale.strip()
    return os.getenv("BSL_LOCALE", "ko-KR")


def _retrieval_cache_key(canonical_key: str, locale: str, top_k: int) -> str:
    return f"rag:ret:{canonical_key}:{locale}:{top_k}"


def _answer_cache_key(canonical_key: str, locale: str) -> str:
    return f"rag:ans:{canonical_key}:{locale}:{_prompt_version()}"


def _build_context(chunks: List[dict[str, Any]]) -> Dict[str, Any]:
    return {
        "chunks": [
            {
                # Force citation keys to retrieved chunk IDs for strict post-check mapping.
                "citation_key": chunk.get("chunk_id") or chunk.get("citation_key"),
                "title": chunk.get("title") or chunk.get("source_title") or "",
                "url": chunk.get("url") or "",
                "content": chunk.get("snippet") or "",
            }
            for chunk in chunks
        ]
    }


def _format_sources(chunks: List[dict[str, Any]]) -> List[dict[str, Any]]:
    sources: List[dict[str, Any]] = []
    for chunk in chunks:
        sources.append(
            {
                "citation_key": chunk.get("citation_key") or chunk.get("chunk_id") or "",
                "doc_id": chunk.get("doc_id") or "",
                "chunk_id": chunk.get("chunk_id") or "",
                "title": chunk.get("title") or chunk.get("source_title") or "",
                "url": chunk.get("url") or "",
                "snippet": chunk.get("snippet") or "",
            }
        )
    return sources


def _fallback_defaults(reason_code: str) -> Dict[str, Any]:
    defaults: Dict[str, Dict[str, Any]] = {
        "NO_MESSAGES": {
            "message": "질문을 입력해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "CHAT_BAD_REQUEST": {
            "message": "요청 형식이 올바르지 않습니다. 질문 내용을 다시 입력해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "CHAT_INVALID_SESSION_ID": {
            "message": "세션 정보 형식이 올바르지 않습니다. 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 1000,
        },
        "CHAT_MESSAGE_TOO_LONG": {
            "message": f"질문이 너무 깁니다. {_chat_max_message_chars()}자 이내로 입력해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_HISTORY_TOO_LONG": {
            "message": f"대화 기록이 너무 깁니다. 최근 {_chat_max_history_turns()}개 발화만 남겨 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_PAYLOAD_TOO_LARGE": {
            "message": f"요청 본문이 너무 큽니다. 총 {_chat_max_total_chars()}자 이하로 줄여 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_TOP_K_TOO_LARGE": {
            "message": f"요청 옵션 값이 너무 큽니다. top_k를 {_chat_max_top_k()} 이하로 설정해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "RAG_NO_CHUNKS": {
            "message": "현재 근거 문서를 찾지 못해 확정 답변을 드리기 어렵습니다. 키워드나 조건을 조금 더 구체적으로 입력해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "RAG_LOW_SCORE": {
            "message": "관련 근거의 신뢰도가 낮아 확정 답변이 어렵습니다. 질문을 구체화하거나 다른 표현으로 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "LLM_NO_CITATIONS": {
            "message": "생성된 답변과 근거 문서가 일치하지 않아 답변을 보류했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "LLM_LOW_CITATION_COVERAGE": {
            "message": "답변이 참조한 근거 범위가 충분하지 않아 확정 답변을 보류했습니다. 질문을 조금 더 구체화해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "PROVIDER_TIMEOUT": {
            "message": "응답 시간이 지연되어 답변을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 3000,
        },
        "OUTPUT_GUARD_EMPTY_ANSWER": {
            "message": "응답 품질 검증에 실패해 답변을 보류했습니다. 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "OUTPUT_GUARD_INSUFFICIENT_CITATIONS": {
            "message": "근거 확인이 충분하지 않아 확정 답변을 제공할 수 없습니다.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "OUTPUT_GUARD_FORBIDDEN_CLAIM": {
            "message": "정책상 확정 답변이 어려운 요청입니다. 주문번호/상세 조건을 포함해 다시 질문해 주세요.",
            "recoverable": True,
            "next_action": "OPEN_SUPPORT_TICKET",
            "retry_after_ms": None,
        },
    }
    return defaults.get(
        reason_code,
        {
            "message": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 3000,
        },
    )


def _fallback(
    trace_id: str,
    request_id: str,
    message: str | None,
    reason_code: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    defaults = _fallback_defaults(reason_code)
    resolved_message = (message or "").strip() or str(defaults["message"])
    fallback_count = _increment_fallback_count(session_id) if session_id else None
    escalated = False
    next_action = str(defaults["next_action"])
    if user_id and fallback_count is not None and fallback_count >= _fallback_escalation_threshold():
        next_action = "OPEN_SUPPORT_TICKET"
        escalated = True
    metrics.inc("chat_fallback_total", {"reason": reason_code})
    metrics.inc(
        "chat_error_recovery_hint_total",
        {
            "next_action": next_action,
            "reason_code": reason_code,
            "source": "rag",
        },
    )
    if escalated:
        metrics.inc("chat_fallback_escalated_total", {"reason": reason_code})
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {
            "role": "assistant",
            "content": resolved_message,
        },
        "sources": [],
        "citations": [],
        "status": "insufficient_evidence",
        "reason_code": reason_code,
        "recoverable": bool(defaults["recoverable"]),
        "next_action": next_action,
        "retry_after_ms": defaults["retry_after_ms"],
        "fallback_count": fallback_count,
        "escalated": escalated,
    }


def _is_high_risk_query(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    return any(keyword in q for keyword in _risk_band_high_keywords())


def _contains_forbidden_claim(answer: str) -> bool:
    text = (answer or "").lower()
    if not text:
        return False
    return any(keyword in text for keyword in _guard_forbidden_answer_keywords())


def _compute_risk_band(query: str, status: str, citations: List[str], guard_reason: Optional[str]) -> str:
    if status in {"error", "insufficient_evidence"}:
        return "R3"
    if guard_reason:
        return "R3"
    high_risk = _is_high_risk_query(query)
    citation_count = len(citations or [])
    if high_risk and citation_count <= 0:
        return "R3"
    if high_risk:
        return "R2"
    if citation_count <= 0:
        return "R1"
    return "R0"


def _guard_answer(
    query: str,
    answer_text: str,
    citations: List[str],
    trace_id: str,
    request_id: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not _output_guard_enabled():
        return None, None
    answer = (answer_text or "").strip()
    if not answer:
        return _fallback(trace_id, request_id, None, "OUTPUT_GUARD_EMPTY_ANSWER", session_id=session_id, user_id=user_id), "OUTPUT_GUARD_EMPTY_ANSWER"

    high_risk = _is_high_risk_query(query)
    min_citations = _guard_high_risk_min_citations() if high_risk else 1
    if len(citations or []) < min_citations:
        return _fallback(
            trace_id,
            request_id,
            None,
            "OUTPUT_GUARD_INSUFFICIENT_CITATIONS",
            session_id=session_id,
            user_id=user_id,
        ), "OUTPUT_GUARD_INSUFFICIENT_CITATIONS"

    if high_risk and _contains_forbidden_claim(answer):
        return _fallback(
            trace_id,
            request_id,
            None,
            "OUTPUT_GUARD_FORBIDDEN_CLAIM",
            session_id=session_id,
            user_id=user_id,
        ), "OUTPUT_GUARD_FORBIDDEN_CLAIM"
    return None, None


def _validate_citations(raw_citations: List[str], chunks: List[dict[str, Any]]) -> List[str]:
    allowed: set[str] = set()
    for chunk in chunks:
        citation_key = chunk.get("citation_key")
        chunk_id = chunk.get("chunk_id")
        if isinstance(citation_key, str) and citation_key:
            allowed.add(citation_key)
        if isinstance(chunk_id, str) and chunk_id:
            allowed.add(chunk_id)
    valid: List[str] = []
    for citation in raw_citations:
        if citation in allowed and citation not in valid:
            valid.append(citation)
    return valid


def _citation_doc_coverage(citations: List[str], chunks: List[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    citation_to_doc: Dict[str, str] = {}
    selected_docs: set[str] = set()
    for chunk in chunks:
        doc_id = str(chunk.get("doc_id") or "").strip()
        if not doc_id:
            continue
        selected_docs.add(doc_id)
        citation_key = str(chunk.get("citation_key") or "").strip()
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if citation_key:
            citation_to_doc[citation_key] = doc_id
        if chunk_id:
            citation_to_doc[chunk_id] = doc_id
    if not selected_docs:
        return 0.0
    cited_docs: set[str] = set()
    for citation in citations:
        doc_id = citation_to_doc.get(str(citation))
        if doc_id:
            cited_docs.add(doc_id)
    return float(len(cited_docs)) / float(len(selected_docs))


def _citation_coverage_threshold(query: str) -> float:
    if _is_high_risk_query(query):
        return _chat_high_risk_min_citation_coverage_ratio()
    return _chat_min_citation_coverage_ratio()


def _is_citation_coverage_sufficient(query: str, citations: List[str], chunks: List[dict[str, Any]]) -> tuple[bool, float, float]:
    coverage = _citation_doc_coverage(citations, chunks)
    threshold = _citation_coverage_threshold(query)
    return coverage >= threshold, coverage, threshold


def _diversity_ratio(chunks: List[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    docs = {str(chunk.get("doc_id") or "") for chunk in chunks if chunk.get("doc_id")}
    return len(docs) / float(len(chunks))


def _bad_retrieval_reason(trace: Dict[str, Any]) -> Optional[str]:
    selected = trace.get("selected") or []
    if not selected:
        return "RAG_NO_CHUNKS"
    top_score = float(selected[0].get("score") or 0.0)
    if top_score <= _bad_score_threshold():
        return "RAG_LOW_SCORE"
    if _diversity_ratio(selected) < _min_diversity_ratio():
        return "RAG_LOW_DIVERSITY"
    return None


def _sse_event(name: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"


def _extract_query_text(request: Dict[str, Any]) -> str:
    message = request.get("message") if isinstance(request.get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""


def _is_valid_session_id(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    session_id = raw.strip()
    if not session_id:
        return False
    if len(session_id) > _chat_session_id_max_len():
        return False
    return _chat_session_id_pattern().fullmatch(session_id) is not None


def _validate_chat_request(request: Dict[str, Any]) -> Optional[str]:
    if not isinstance(request, dict):
        return "CHAT_BAD_REQUEST"
    message = request.get("message")
    if not isinstance(message, dict):
        return "CHAT_BAD_REQUEST"
    content = message.get("content")
    if content is None:
        return "NO_MESSAGES"
    if not isinstance(content, str):
        return "CHAT_BAD_REQUEST"
    query = content.strip()
    if not query:
        return "NO_MESSAGES"
    if len(query) > _chat_max_message_chars():
        return "CHAT_MESSAGE_TOO_LONG"

    history = request.get("history")
    if history is not None and not isinstance(history, list):
        return "CHAT_BAD_REQUEST"
    history_items = history if isinstance(history, list) else []
    if len(history_items) > _chat_max_history_turns():
        return "CHAT_HISTORY_TOO_LONG"

    total_chars = len(query)
    for item in history_items:
        if not isinstance(item, dict):
            return "CHAT_BAD_REQUEST"
        text = item.get("content")
        if not isinstance(text, str):
            return "CHAT_BAD_REQUEST"
        if len(text) > _chat_max_message_chars():
            return "CHAT_MESSAGE_TOO_LONG"
        total_chars += len(text)

    if total_chars > _chat_max_total_chars():
        return "CHAT_PAYLOAD_TOO_LARGE"

    options = request.get("options")
    if options is not None and not isinstance(options, dict):
        return "CHAT_BAD_REQUEST"
    if isinstance(options, dict):
        top_k = options.get("top_k")
        if top_k is not None and (not isinstance(top_k, int) or top_k < 1):
            return "CHAT_BAD_REQUEST"
        if isinstance(top_k, int) and top_k > _chat_max_top_k():
            return "CHAT_TOP_K_TOO_LARGE"

    session_id = request.get("session_id")
    if session_id is not None and not _is_valid_session_id(session_id):
        return "CHAT_INVALID_SESSION_ID"
    return None


def _extract_user_id(request: Dict[str, Any]) -> Optional[str]:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    user_id = client.get("user_id") if isinstance(client, dict) else None
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return None


def _resolve_session_id(request: Dict[str, Any], user_id: Optional[str]) -> str:
    session_id = request.get("session_id")
    if _is_valid_session_id(session_id):
        return str(session_id).strip()
    if user_id:
        return f"u:{user_id}:default"
    return "anon:default"


def _fallback_escalation_threshold() -> int:
    return max(2, int(os.getenv("QS_CHAT_FALLBACK_ESCALATE_THRESHOLD", "3")))


def _fallback_counter_key(session_id: str) -> str:
    return f"chat:fallback:count:{session_id}"


def _increment_fallback_count(session_id: str) -> int:
    key = _fallback_counter_key(session_id)
    cached = _CACHE.get_json(key)
    count = 0
    if isinstance(cached, dict):
        raw_count = cached.get("count")
        if isinstance(raw_count, int) and raw_count >= 0:
            count = raw_count
    count += 1
    _CACHE.set_json(key, {"count": count}, ttl=max(60, _answer_cache_ttl_sec() * 2))
    return count


def _reset_fallback_count(session_id: Optional[str]) -> None:
    if not session_id:
        return
    _CACHE.set_json(_fallback_counter_key(session_id), {"count": 0}, ttl=5)


def _unresolved_context_key(session_id: str) -> str:
    return f"chat:unresolved:{session_id}"


def _save_unresolved_context(
    session_id: Optional[str],
    query: str,
    reason_code: str,
    *,
    trace_id: str,
    request_id: str,
) -> None:
    if not session_id:
        return
    trimmed_query = (query or "").strip()
    _CACHE.set_json(
        _unresolved_context_key(session_id),
        {
            "query": trimmed_query,
            "reason_code": reason_code,
            "trace_id": trace_id,
            "request_id": request_id,
            "updated_at": int(time.time()),
        },
        ttl=_unresolved_context_ttl_sec(),
    )


def _clear_unresolved_context(session_id: Optional[str]) -> None:
    if not session_id:
        return
    _CACHE.set_json(_unresolved_context_key(session_id), {"cleared": True}, ttl=1)


def _resolve_top_k(request: Dict[str, Any]) -> int:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    top_k = options.get("top_k")
    if isinstance(top_k, int) and top_k > 0:
        return min(top_k, _chat_max_top_k())
    return min(int(os.getenv("QS_RAG_TOP_K", "6")), _chat_max_top_k())


def _resolve_top_n(request: Dict[str, Any]) -> Optional[int]:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    top_n = options.get("top_n")
    if isinstance(top_n, int) and top_n > 0:
        return top_n
    return None


def _resolve_rerank_override(request: Dict[str, Any]) -> Optional[bool]:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    rerank = options.get("rag_rerank")
    if isinstance(rerank, bool):
        return rerank
    return None


async def _retrieve_with_optional_rewrite(
    request: Dict[str, Any],
    query: str,
    canonical_key: str,
    locale: str,
    trace_id: str,
    request_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    top_k = _resolve_top_k(request)
    top_n = _resolve_top_n(request)
    rerank_override = _resolve_rerank_override(request)
    retrieval_cache_key = _retrieval_cache_key(canonical_key, locale, top_k)

    cached_trace = _CACHE.get_json(retrieval_cache_key)
    if isinstance(cached_trace, dict) and cached_trace.get("trace"):
        metrics.inc("chat_requests_total", {"decision": "retrieval_cache_hit"})
        trace = cached_trace.get("trace")
        return trace, {
            "retrieval_cache_hit": True,
            "rewrite_applied": False,
            "rewrite_reason": None,
            "rewrite_strategy": "none",
            "rewritten_query": query,
            "initial_query": query,
            "bad_reason": _bad_retrieval_reason(trace),
        }

    trace = await retrieve_chunks_with_trace(
        query,
        trace_id,
        request_id,
        top_k=top_k,
        top_n=top_n,
        rerank_enabled=rerank_override,
    )
    bad_reason = _bad_retrieval_reason(trace)
    rewrite_meta = {
        "retrieval_cache_hit": False,
        "rewrite_applied": False,
        "rewrite_reason": bad_reason,
        "rewrite_strategy": "none",
        "rewritten_query": query,
        "initial_query": query,
        "bad_reason": bad_reason,
    }

    if bad_reason and _rewrite_on_bad_enabled():
        candidates = await retrieve_candidates(query, trace_id, request_id, top_k=5)
        rewrite_payload, rewrite_detail = await run_rewrite(
            query,
            trace_id,
            request_id,
            reason=bad_reason,
            locale=locale,
            candidates=candidates,
        )
        rewritten = rewrite_payload.get("rewritten") if isinstance(rewrite_payload, dict) else None
        if rewrite_payload.get("applied") and isinstance(rewritten, str) and rewritten.strip() and rewritten.strip() != query.strip():
            rewrite_meta["rewrite_applied"] = True
            rewrite_meta["rewrite_strategy"] = rewrite_payload.get("method") or "rewrite"
            rewrite_meta["rewritten_query"] = rewritten.strip()
            trace2 = await retrieve_chunks_with_trace(
                rewritten.strip(),
                trace_id,
                request_id,
                top_k=top_k,
                top_n=top_n,
                rerank_enabled=rerank_override,
            )
            selected_before = trace.get("selected") or []
            selected_after = trace2.get("selected") or []
            if len(selected_after) > len(selected_before) or (selected_before and selected_after and float(selected_after[0].get("score") or 0.0) > float(selected_before[0].get("score") or 0.0)):
                trace = trace2
                rewrite_meta["rewrite_reason"] = bad_reason
            else:
                rewrite_meta["rewrite_reason"] = "rewrite_not_improved"
        else:
            reject_reason = rewrite_detail.get("reject_reason") if isinstance(rewrite_detail, dict) else None
            rewrite_meta["rewrite_reason"] = str(reject_reason or bad_reason)

    _CACHE.set_json(retrieval_cache_key, {"trace": trace}, ttl=max(1, _retrieval_cache_ttl_sec()))
    return trace, rewrite_meta


def _build_llm_payload(request: Dict[str, Any], trace_id: str, request_id: str, query: str, chunks: List[dict[str, Any]]) -> Dict[str, Any]:
    messages: List[dict[str, Any]] = [{"role": "system", "content": "Answer using provided sources and cite them."}]
    history = request.get("history") or []
    if isinstance(history, list):
        for item in history[-6:]:
            if isinstance(item, dict) and item.get("role") and item.get("content"):
                messages.append({"role": item.get("role"), "content": item.get("content")})
    messages.append({"role": "user", "content": query})
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "model": _llm_model(),
        "messages": messages,
        "context": _build_context(chunks),
        "citations_required": True,
    }


async def _call_llm_json(payload: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    started = time.perf_counter()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{_llm_url()}/v1/generate", json=payload, headers=headers, timeout=_llm_timeout_sec())
        response.raise_for_status()
        data = response.json()
    took_ms = int((time.perf_counter() - started) * 1000)
    metrics.inc("llm_generate_latency_ms", value=max(0, took_ms))
    return data


async def _stream_llm(
    payload: Dict[str, Any],
    trace_id: str,
    request_id: str,
) -> tuple[AsyncIterator[str], dict[str, Any]]:
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    first_token_reported = False
    started = time.perf_counter()
    stream_state: dict[str, Any] = {
        "answer": "",
        "citations": [],
        "llm_error": None,
        "done_status": "ok",
    }

    async def generator() -> AsyncIterator[str]:
        nonlocal first_token_reported
        event_name = "message"
        data_lines: List[str] = []
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{_llm_url()}/v1/generate?stream=true",
                    json={**payload, "stream": True},
                    headers=headers,
                    timeout=_llm_timeout_sec(),
                ) as response:
                    response.raise_for_status()
                    async for raw_line in response.aiter_lines():
                        line = raw_line if raw_line is not None else ""
                        if line.startswith("event:"):
                            event_name = line.split(":", 1)[1].strip() or "message"
                        elif line.startswith("data:"):
                            data_lines.append(line.split(":", 1)[1].strip())
                        elif line == "":
                            if not data_lines:
                                event_name = "message"
                                continue
                            data = "\n".join(data_lines)
                            if event_name == "delta":
                                if not first_token_reported:
                                    first_token_reported = True
                                    first_token_ms = int((time.perf_counter() - started) * 1000)
                                    metrics.inc("chat_first_token_latency_ms", value=max(0, first_token_ms))
                                try:
                                    parsed = json.loads(data)
                                    delta = parsed.get("delta") if isinstance(parsed, dict) else None
                                    if isinstance(delta, str):
                                        stream_state["answer"] += delta
                                except Exception:
                                    stream_state["answer"] += data
                            elif event_name == "done":
                                try:
                                    parsed = json.loads(data)
                                    if isinstance(parsed, dict):
                                        done_status = parsed.get("status")
                                        if isinstance(done_status, str) and done_status:
                                            stream_state["done_status"] = done_status
                                        if isinstance(parsed.get("citations"), list):
                                            stream_state["citations"] = [str(item) for item in parsed.get("citations") if isinstance(item, str)]
                                except Exception:
                                    pass
                                data_lines = []
                                event_name = "message"
                                continue
                            yield _sse_event(event_name, data)
                            data_lines = []
                            event_name = "message"
            took_ms = int((time.perf_counter() - started) * 1000)
            metrics.inc("llm_generate_latency_ms", value=max(0, took_ms))
        except Exception as exc:
            stream_state["llm_error"] = str(exc)
            metrics.inc("chat_fallback_total", {"reason": "PROVIDER_TIMEOUT"})
            yield _sse_event("error", {"code": "PROVIDER_TIMEOUT", "message": "LLM 응답 지연으로 처리하지 못했습니다."})
            yield _sse_event("done", {"status": "error", "citations": []})

    return generator(), stream_state


async def _prepare_chat(
    request: Dict[str, Any],
    trace_id: str,
    request_id: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    query = _extract_query_text(request)
    if not query.strip():
        return {
            "ok": False,
            "reason": "NO_MESSAGES",
            "response": _fallback(trace_id, request_id, None, "NO_MESSAGES", session_id=session_id, user_id=user_id),
        }

    locale = _locale_from_request(request)
    canonical_key = _canonical_key(query, locale)
    trace, rewrite_meta = await _retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id)
    selected = trace.get("selected") or []
    if not selected:
        return {
            "ok": False,
            "reason": "RAG_NO_CHUNKS",
            "response": _fallback(trace_id, request_id, None, "RAG_NO_CHUNKS", session_id=session_id, user_id=user_id),
            "canonical_key": canonical_key,
            "locale": locale,
            "trace": trace,
            "rewrite": rewrite_meta,
        }

    return {
        "ok": True,
        "query": rewrite_meta.get("rewritten_query") or query,
        "canonical_key": canonical_key,
        "locale": locale,
        "trace": trace,
        "rewrite": rewrite_meta,
        "selected": selected,
    }


async def run_chat(request: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    user_id = _extract_user_id(request)
    session_id = _resolve_session_id(request, user_id)
    query_text = _extract_query_text(request)
    validation_reason = _validate_chat_request(request)
    if validation_reason:
        metrics.inc("chat_validation_fail_total", {"reason": validation_reason})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, validation_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(session_id, query_text, validation_reason, trace_id=trace_id, request_id=request_id)
        return response
    tool_response = await run_tool_chat(request, trace_id, request_id)
    if tool_response is not None:
        _reset_fallback_count(session_id)
        _clear_unresolved_context(session_id)
        metrics.inc("chat_requests_total", {"decision": "tool_path"})
        return tool_response

    prepared = await _prepare_chat(request, trace_id, request_id, session_id=session_id, user_id=user_id)
    if not prepared.get("ok"):
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = prepared.get("response")
        if isinstance(response, dict):
            _save_unresolved_context(
                session_id,
                query_text,
                str(response.get("reason_code") or str(prepared.get("reason") or "RAG_NO_CHUNKS")),
                trace_id=trace_id,
                request_id=request_id,
            )
        return response

    query = prepared.get("query") or ""
    canonical_key = prepared.get("canonical_key")
    locale = prepared.get("locale")
    selected = prepared.get("selected") or []
    answer_cache_key = _answer_cache_key(canonical_key, locale)

    if _answer_cache_enabled():
        cached = _CACHE.get_json(answer_cache_key)
        if isinstance(cached, dict) and cached.get("response"):
            _reset_fallback_count(session_id)
            _clear_unresolved_context(session_id)
            metrics.inc("chat_requests_total", {"decision": "answer_cache_hit"})
            return cached.get("response")

    payload = _build_llm_payload(request, trace_id, request_id, query, selected)
    try:
        data = await _call_llm_json(payload, trace_id, request_id)
    except Exception:
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, "PROVIDER_TIMEOUT", session_id=session_id, user_id=user_id)
        _save_unresolved_context(session_id, query, "PROVIDER_TIMEOUT", trace_id=trace_id, request_id=request_id)
        return response

    answer_text = str(data.get("content") or "")
    raw_citations = data.get("citations") if isinstance(data.get("citations"), list) else _extract_citations_from_text(answer_text)
    citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
    if not citations:
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, "LLM_NO_CITATIONS", session_id=session_id, user_id=user_id)
        _save_unresolved_context(session_id, query, "LLM_NO_CITATIONS", trace_id=trace_id, request_id=request_id)
        return response
    coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
    if not coverage_ok:
        metrics.inc(
            "chat_citation_coverage_block_total",
            {
                "risk": "high" if _is_high_risk_query(query) else "normal",
                "threshold": f"{coverage_threshold:.2f}",
            },
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, "LLM_LOW_CITATION_COVERAGE", session_id=session_id, user_id=user_id)
        _save_unresolved_context(session_id, query, "LLM_LOW_CITATION_COVERAGE", trace_id=trace_id, request_id=request_id)
        return response

    guarded_response, guard_reason = _guard_answer(
        query,
        answer_text,
        citations,
        trace_id,
        request_id,
        session_id=session_id,
        user_id=user_id,
    )
    if guarded_response is not None:
        metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
        metrics.inc(
            "chat_answer_risk_band_total",
            {"band": _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)},
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        _save_unresolved_context(
            session_id,
            query,
            str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
            trace_id=trace_id,
            request_id=request_id,
        )
        return guarded_response

    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {"role": "assistant", "content": answer_text},
        "sources": _format_sources(selected),
        "citations": citations,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
        "fallback_count": 0,
        "escalated": False,
    }
    metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
    metrics.inc("chat_answer_risk_band_total", {"band": _compute_risk_band(query, "ok", citations, None)})
    if _answer_cache_enabled():
        _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))

    _reset_fallback_count(session_id)
    _clear_unresolved_context(session_id)
    metrics.inc("chat_requests_total", {"decision": "ok"})
    return response


async def run_chat_stream(request: Dict[str, Any], trace_id: str, request_id: str) -> AsyncIterator[str]:
    user_id = _extract_user_id(request)
    session_id = _resolve_session_id(request, user_id)
    query_text = _extract_query_text(request)
    validation_reason = _validate_chat_request(request)
    if validation_reason:
        metrics.inc("chat_validation_fail_total", {"reason": validation_reason})
        response = _fallback(trace_id, request_id, None, validation_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(session_id, query_text, validation_reason, trace_id=trace_id, request_id=request_id)
        risk_band = _compute_risk_band("", response.get("status", "insufficient_evidence"), [], validation_reason)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": response.get("status"),
                "risk_band": risk_band,
                "reason_code": response.get("reason_code"),
                "recoverable": response.get("recoverable"),
                "next_action": response.get("next_action"),
                "retry_after_ms": response.get("retry_after_ms"),
                "fallback_count": response.get("fallback_count"),
                "escalated": response.get("escalated"),
            },
        )
        yield _sse_event("delta", {"delta": str(response.get("answer", {}).get("content") if isinstance(response.get("answer"), dict) else "")})
        yield _sse_event(
            "done",
            {
                "status": response.get("status"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": response.get("reason_code"),
                "recoverable": response.get("recoverable"),
                "next_action": response.get("next_action"),
                "retry_after_ms": response.get("retry_after_ms"),
                "fallback_count": response.get("fallback_count"),
                "escalated": response.get("escalated"),
            },
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    tool_response = await run_tool_chat(request, trace_id, request_id)
    if tool_response is not None:
        _reset_fallback_count(session_id)
        _clear_unresolved_context(session_id)
        answer = tool_response.get("answer", {}) if isinstance(tool_response.get("answer"), dict) else {}
        citations = [str(item) for item in (tool_response.get("citations") or []) if isinstance(item, str)]
        sources = tool_response.get("sources") if isinstance(tool_response.get("sources"), list) else []
        status = str(tool_response.get("status") or "ok")
        reason_code = str(tool_response.get("reason_code") or "OK")
        recoverable = bool(tool_response.get("recoverable")) if isinstance(tool_response.get("recoverable"), bool) else False
        next_action = str(tool_response.get("next_action") or "NONE")
        retry_after_ms = tool_response.get("retry_after_ms")
        fallback_count = tool_response.get("fallback_count")
        escalated = bool(tool_response.get("escalated")) if isinstance(tool_response.get("escalated"), bool) else False
        risk_band = _compute_risk_band(_extract_query_text(request), status, citations, None)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "tool_path",
                "sources": sources,
                "citations": citations,
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        yield _sse_event("delta", {"delta": str(answer.get("content") or "")})
        yield _sse_event(
            "done",
            {
                "status": status,
                "citations": citations,
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "tool_path"})
        return

    prepared = await _prepare_chat(request, trace_id, request_id, session_id=session_id, user_id=user_id)
    if not prepared.get("ok"):
        response = prepared.get("response") or _fallback(
            trace_id,
            request_id,
            None,
            "RAG_NO_CHUNKS",
            session_id=session_id,
            user_id=user_id,
        )
        answer = response.get("answer", {}).get("content") if isinstance(response.get("answer"), dict) else ""
        reason_code = str(response.get("reason_code") or "RAG_NO_CHUNKS")
        recoverable = bool(response.get("recoverable")) if isinstance(response.get("recoverable"), bool) else True
        next_action = str(response.get("next_action") or "REFINE_QUERY")
        retry_after_ms = response.get("retry_after_ms")
        fallback_count = response.get("fallback_count")
        escalated = bool(response.get("escalated")) if isinstance(response.get("escalated"), bool) else False
        risk_band = _compute_risk_band("", response.get("status", "insufficient_evidence"), [], "RAG_NO_CHUNKS")
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "fallback",
                "sources": [],
                "citations": [],
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        yield _sse_event("delta", {"delta": answer})
        yield _sse_event(
            "done",
            {
                "status": response.get("status", "insufficient_evidence"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        _save_unresolved_context(
            session_id,
            query_text,
            str(reason_code or str(prepared.get("reason") or "RAG_NO_CHUNKS")),
            trace_id=trace_id,
            request_id=request_id,
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    query = prepared.get("query") or ""
    canonical_key = prepared.get("canonical_key")
    locale = prepared.get("locale")
    selected = prepared.get("selected") or []
    sources = _format_sources(selected)
    answer_cache_key = _answer_cache_key(canonical_key, locale)

    if _answer_cache_enabled():
        cached = _CACHE.get_json(answer_cache_key)
        if isinstance(cached, dict) and isinstance(cached.get("response"), dict):
            cached_response = cached.get("response")
            cached_answer = cached_response.get("answer") if isinstance(cached_response.get("answer"), dict) else {}
            cached_citations = [str(item) for item in (cached_response.get("citations") or []) if isinstance(item, str)]
            cached_status = str(cached_response.get("status") or "ok")
            cached_reason_code = str(cached_response.get("reason_code") or "OK")
            cached_recoverable = (
                bool(cached_response.get("recoverable")) if isinstance(cached_response.get("recoverable"), bool) else False
            )
            cached_next_action = str(cached_response.get("next_action") or "NONE")
            cached_retry_after_ms = cached_response.get("retry_after_ms")
            cached_fallback_count = cached_response.get("fallback_count")
            cached_escalated = bool(cached_response.get("escalated")) if isinstance(cached_response.get("escalated"), bool) else False
            risk_band = _compute_risk_band(query, cached_status, cached_citations, None)
            yield _sse_event(
                "meta",
                {
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "status": "cached",
                    "sources": sources,
                    "citations": cached_citations,
                    "risk_band": risk_band,
                    "reason_code": cached_reason_code,
                    "recoverable": cached_recoverable,
                    "next_action": cached_next_action,
                    "retry_after_ms": cached_retry_after_ms,
                    "fallback_count": cached_fallback_count,
                    "escalated": cached_escalated,
                },
            )
            yield _sse_event("delta", {"delta": cached_answer.get("content") or ""})
            yield _sse_event(
                "done",
                {
                    "status": cached_status,
                    "citations": cached_citations,
                    "risk_band": risk_band,
                    "reason_code": cached_reason_code,
                    "recoverable": cached_recoverable,
                    "next_action": cached_next_action,
                    "retry_after_ms": cached_retry_after_ms,
                    "fallback_count": cached_fallback_count,
                    "escalated": cached_escalated,
                },
            )
            _reset_fallback_count(session_id)
            _clear_unresolved_context(session_id)
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "answer_cache_hit"})
            return

    payload = _build_llm_payload(request, trace_id, request_id, query, selected)
    if not _llm_stream_enabled():
        try:
            data = await _call_llm_json(payload, trace_id, request_id)
            answer_text = str(data.get("content") or "")
            raw_citations = data.get("citations") if isinstance(data.get("citations"), list) else _extract_citations_from_text(answer_text)
            citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
            if not citations:
                yield _sse_event("error", {"code": "LLM_NO_CITATIONS", "message": "근거 문서 매핑에 실패했습니다."})
                risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_NO_CITATIONS")
                fallback_response = _fallback(
                    trace_id,
                    request_id,
                    None,
                    "LLM_NO_CITATIONS",
                    session_id=session_id,
                    user_id=user_id,
                )
                yield _sse_event(
                    "done",
                    {
                        "status": "insufficient_evidence",
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": fallback_response.get("reason_code"),
                        "recoverable": fallback_response.get("recoverable"),
                        "next_action": fallback_response.get("next_action"),
                        "retry_after_ms": fallback_response.get("retry_after_ms"),
                        "fallback_count": fallback_response.get("fallback_count"),
                        "escalated": fallback_response.get("escalated"),
                    },
                )
                _save_unresolved_context(session_id, query, "LLM_NO_CITATIONS", trace_id=trace_id, request_id=request_id)
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return
            coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
            if not coverage_ok:
                metrics.inc(
                    "chat_citation_coverage_block_total",
                    {
                        "risk": "high" if _is_high_risk_query(query) else "normal",
                        "threshold": f"{coverage_threshold:.2f}",
                    },
                )
                yield _sse_event("error", {"code": "LLM_LOW_CITATION_COVERAGE", "message": "근거 커버리지가 부족합니다."})
                risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_LOW_CITATION_COVERAGE")
                fallback_response = _fallback(
                    trace_id,
                    request_id,
                    None,
                    "LLM_LOW_CITATION_COVERAGE",
                    session_id=session_id,
                    user_id=user_id,
                )
                yield _sse_event(
                    "done",
                    {
                        "status": "insufficient_evidence",
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": fallback_response.get("reason_code"),
                        "recoverable": fallback_response.get("recoverable"),
                        "next_action": fallback_response.get("next_action"),
                        "retry_after_ms": fallback_response.get("retry_after_ms"),
                        "fallback_count": fallback_response.get("fallback_count"),
                        "escalated": fallback_response.get("escalated"),
                    },
                )
                _save_unresolved_context(session_id, query, "LLM_LOW_CITATION_COVERAGE", trace_id=trace_id, request_id=request_id)
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return

            guarded_response, guard_reason = _guard_answer(
                query,
                answer_text,
                citations,
                trace_id,
                request_id,
                session_id=session_id,
                user_id=user_id,
            )
            if guarded_response is not None:
                metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
                risk_band = _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)
                yield _sse_event(
                    "meta",
                    {
                        "trace_id": trace_id,
                        "request_id": request_id,
                        "status": "guard_blocked",
                        "sources": sources,
                        "citations": [],
                        "risk_band": risk_band,
                    },
                )
                yield _sse_event("error", {"code": guard_reason or "OUTPUT_GUARD_BLOCKED", "message": "output guard blocked"})
                yield _sse_event(
                    "done",
                    {
                        "status": guarded_response.get("status", "insufficient_evidence"),
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": guarded_response.get("reason_code"),
                        "recoverable": guarded_response.get("recoverable"),
                        "next_action": guarded_response.get("next_action"),
                        "retry_after_ms": guarded_response.get("retry_after_ms"),
                        "fallback_count": guarded_response.get("fallback_count"),
                        "escalated": guarded_response.get("escalated"),
                    },
                )
                _save_unresolved_context(
                    session_id,
                    query,
                    str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
                    trace_id=trace_id,
                    request_id=request_id,
                )
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return

            risk_band = _compute_risk_band(query, "ok", citations, None)
            metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
            yield _sse_event(
                "meta",
                {
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "status": "ok",
                    "sources": sources,
                    "citations": citations,
                    "risk_band": risk_band,
                "reason_code": "OK",
                "recoverable": False,
                "next_action": "NONE",
                "retry_after_ms": None,
                "fallback_count": 0,
                "escalated": False,
            },
        )
            yield _sse_event("delta", {"delta": answer_text})
            yield _sse_event(
                "done",
                {
                    "status": "ok",
                    "citations": citations,
                    "risk_band": risk_band,
                    "reason_code": "OK",
                    "recoverable": False,
                    "next_action": "NONE",
                    "retry_after_ms": None,
                    "fallback_count": 0,
                    "escalated": False,
                },
            )
            response = {
                "version": "v1",
                "trace_id": trace_id,
                "request_id": request_id,
                "answer": {"role": "assistant", "content": answer_text},
                "sources": _format_sources(selected),
                "citations": citations,
                "status": "ok",
                "reason_code": "OK",
                "recoverable": False,
                "next_action": "NONE",
                "retry_after_ms": None,
                "fallback_count": 0,
                "escalated": False,
            }
            if _answer_cache_enabled():
                _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))
            _reset_fallback_count(session_id)
            _clear_unresolved_context(session_id)
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "ok"})
            return
        except Exception:
            yield _sse_event("error", {"code": "PROVIDER_TIMEOUT", "message": "LLM 응답 지연으로 처리하지 못했습니다."})
            risk_band = _compute_risk_band(query, "error", [], "PROVIDER_TIMEOUT")
            fallback_response = _fallback(
                trace_id,
                request_id,
                None,
                "PROVIDER_TIMEOUT",
                session_id=session_id,
                user_id=user_id,
            )
            yield _sse_event(
                "done",
                {
                    "status": "error",
                    "citations": [],
                    "risk_band": risk_band,
                    "reason_code": fallback_response.get("reason_code"),
                    "recoverable": fallback_response.get("recoverable"),
                    "next_action": fallback_response.get("next_action"),
                    "retry_after_ms": fallback_response.get("retry_after_ms"),
                    "fallback_count": fallback_response.get("fallback_count"),
                    "escalated": fallback_response.get("escalated"),
                },
            )
            _save_unresolved_context(session_id, query, "PROVIDER_TIMEOUT", trace_id=trace_id, request_id=request_id)
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "fallback"})
            return

    yield _sse_event(
        "meta",
        {
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "streaming",
            "sources": sources,
            "citations": [],
            "reason_code": "IN_PROGRESS",
            "recoverable": True,
            "next_action": "WAIT",
            "retry_after_ms": None,
            "fallback_count": None,
            "escalated": False,
        },
    )
    stream_iter, stream_state = await _stream_llm(payload, trace_id, request_id)
    async for event in stream_iter:
        if event.startswith("event: done"):
            continue
        if event.startswith("event: meta"):
            continue
        yield event

    if stream_state.get("llm_error"):
        risk_band = _compute_risk_band(query, "error", [], "PROVIDER_TIMEOUT")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "PROVIDER_TIMEOUT",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "error",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "PROVIDER_TIMEOUT", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    answer_text = stream_state.get("answer") or ""
    raw_citations = stream_state.get("citations") or _extract_citations_from_text(answer_text)
    citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
    if not citations:
        metrics.inc("chat_fallback_total", {"reason": "LLM_NO_CITATIONS"})
        yield _sse_event("error", {"code": "LLM_NO_CITATIONS", "message": "근거 문서 매핑에 실패했습니다."})
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_NO_CITATIONS")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "LLM_NO_CITATIONS",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "insufficient_evidence",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "LLM_NO_CITATIONS", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
    if not coverage_ok:
        metrics.inc(
            "chat_citation_coverage_block_total",
            {
                "risk": "high" if _is_high_risk_query(query) else "normal",
                "threshold": f"{coverage_threshold:.2f}",
            },
        )
        yield _sse_event("error", {"code": "LLM_LOW_CITATION_COVERAGE", "message": "근거 커버리지가 부족합니다."})
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_LOW_CITATION_COVERAGE")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "LLM_LOW_CITATION_COVERAGE",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "insufficient_evidence",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "LLM_LOW_CITATION_COVERAGE", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    guarded_response, guard_reason = _guard_answer(
        query,
        answer_text,
        citations,
        trace_id,
        request_id,
        session_id=session_id,
        user_id=user_id,
    )
    if guarded_response is not None:
        metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
        risk_band = _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)
        yield _sse_event("error", {"code": guard_reason or "OUTPUT_GUARD_BLOCKED", "message": "output guard blocked"})
        yield _sse_event(
            "done",
            {
                "status": guarded_response.get("status", "insufficient_evidence"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": guarded_response.get("reason_code"),
                "recoverable": guarded_response.get("recoverable"),
                "next_action": guarded_response.get("next_action"),
                "retry_after_ms": guarded_response.get("retry_after_ms"),
                "fallback_count": guarded_response.get("fallback_count"),
                "escalated": guarded_response.get("escalated"),
            },
        )
        _save_unresolved_context(
            session_id,
            query,
            str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
            trace_id=trace_id,
            request_id=request_id,
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {"role": "assistant", "content": answer_text},
        "sources": _format_sources(selected),
        "citations": citations,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
    }
    if _answer_cache_enabled():
        _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))

    final_status = stream_state.get("done_status") or "ok"
    risk_band = _compute_risk_band(query, final_status, citations, None)
    metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
    metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
    _reset_fallback_count(session_id)
    _clear_unresolved_context(session_id)
    yield _sse_event(
        "done",
        {
            "status": final_status,
            "citations": citations,
            "risk_band": risk_band,
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "fallback_count": 0,
            "escalated": False,
        },
    )
    metrics.inc("chat_requests_total", {"decision": "ok"})


async def explain_chat_rag(request: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    query = _extract_query_text(request)
    if not query.strip():
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "error",
            "reason_codes": ["NO_MESSAGES"],
            "query": {"text": ""},
            "retrieval": {"lexical": [], "vector": [], "fused": [], "selected": []},
        }

    locale = _locale_from_request(request)
    canonical_key = _canonical_key(query, locale)
    trace, rewrite_meta = await _retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id)

    reason_codes = list(trace.get("reason_codes") or [])
    if rewrite_meta.get("rewrite_applied"):
        reason_codes.append("REWRITE_APPLIED")
    if rewrite_meta.get("rewrite_reason"):
        reason_codes.append(str(rewrite_meta.get("rewrite_reason")))

    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "query": {
            "text": query,
            "locale": locale,
            "canonical_key": canonical_key,
            "rewritten": rewrite_meta.get("rewritten_query"),
        },
        "rewrite": rewrite_meta,
        "retrieval": {
            "top_n": trace.get("top_n"),
            "top_k": trace.get("top_k"),
            "lexical": trace.get("lexical") or [],
            "vector": trace.get("vector") or [],
            "fused": trace.get("fused") or [],
            "selected": trace.get("selected") or [],
            "rerank": trace.get("rerank") or {},
            "took_ms": trace.get("took_ms") or 0,
            "degraded": bool(trace.get("degraded")),
        },
        "reason_codes": reason_codes,
    }
