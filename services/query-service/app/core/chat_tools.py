from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from typing import Any

import httpx

from app.core.chat_action_protocol import build_action_draft
from app.core.chat_action_protocol import validate_action_draft
from app.core.chat_book_normalization import BookQuerySlots
from app.core.chat_book_normalization import canonical_book_query
from app.core.chat_book_normalization import extract_book_query_slots
from app.core.chat_book_normalization import normalize_isbn
from app.core.chat_book_normalization import slots_to_dict
from app.core.chat_policy_engine import build_understanding
from app.core.chat_policy_engine import decide_route
from app.core.chat_policy_engine import infer_risk_level
from app.core.chat_policy_engine import PolicyDecision
from app.core.chat_policy_engine import ROUTE_ANSWER
from app.core.chat_policy_engine import ROUTE_ASK
from app.core.chat_policy_engine import ROUTE_CONFIRM
from app.core.chat_policy_engine import ROUTE_OPTIONS
from app.core.cache import get_cache
from app.core.chat_state_store import append_action_audit
from app.core.chat_state_store import get_session_state as get_durable_chat_session_state
from app.core.chat_state_store import upsert_session_state
from app.core.metrics import metrics
from app.core.rag_candidates import retrieve_candidates

_CACHE = get_cache()
_WORKFLOW_PENDING_STATES = {"AWAITING_CONFIRMATION", "CONFIRMED", "FAILED_RETRYABLE", "EXECUTING"}
_WORKFLOW_TERMINAL_STATES = {"EXECUTED", "ABORTED", "EXPIRED", "FAILED_FINAL"}
_WORKFLOW_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "INIT": {"AWAITING_CONFIRMATION"},
    "AWAITING_CONFIRMATION": {"CONFIRMED", "ABORTED", "EXPIRED"},
    "CONFIRMED": {"EXECUTING", "ABORTED", "EXPIRED"},
    "EXECUTING": {"EXECUTED", "FAILED_RETRYABLE", "FAILED_FINAL"},
    "FAILED_RETRYABLE": {"CONFIRMED", "ABORTED", "EXPIRED", "FAILED_FINAL"},
}


@dataclass
class ToolIntent:
    name: str
    confidence: float


@dataclass
class OrderRef:
    order_id: int | None
    order_no: str | None


class ToolCallError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _tool_enabled() -> bool:
    return str(os.getenv("QS_CHAT_TOOL_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _commerce_base_url() -> str:
    return os.getenv("QS_COMMERCE_URL", "http://localhost:8091/api/v1").rstrip("/")


def _tool_lookup_timeout_sec() -> float:
    return float(os.getenv("QS_CHAT_TOOL_LOOKUP_TIMEOUT_SEC", "2.5"))


def _tool_lookup_retry_count() -> int:
    return max(0, int(os.getenv("QS_CHAT_TOOL_LOOKUP_RETRY", "1")))


def _tool_circuit_fail_threshold() -> int:
    return max(1, int(os.getenv("QS_CHAT_TOOL_CIRCUIT_FAIL_THRESHOLD", "3")))


def _tool_circuit_open_sec() -> int:
    return max(1, int(os.getenv("QS_CHAT_TOOL_CIRCUIT_OPEN_SEC", "30")))


def _policy_base_shipping_fee() -> int:
    return max(0, int(os.getenv("QS_CHAT_POLICY_BASE_SHIPPING_FEE", "3000")))


def _policy_fast_shipping_fee() -> int:
    return max(0, int(os.getenv("QS_CHAT_POLICY_FAST_SHIPPING_FEE", "5000")))


def _policy_free_shipping_threshold() -> int:
    return max(0, int(os.getenv("QS_CHAT_POLICY_FREE_SHIPPING_THRESHOLD", "20000")))


def _policy_topic_cache_ttl_sec() -> int:
    return max(30, int(os.getenv("QS_CHAT_POLICY_TOPIC_CACHE_TTL_SEC", "300")))


def _workflow_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_WORKFLOW_TTL_SEC", "900")))


def _confirmation_token_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_CONFIRM_TOKEN_TTL_SEC", "300")))


def _workflow_retry_budget() -> int:
    return max(0, int(os.getenv("QS_CHAT_WORKFLOW_MAX_RETRY", "1")))


def _workflow_action_receipt_ttl_sec() -> int:
    return max(300, int(os.getenv("QS_CHAT_ACTION_RECEIPT_TTL_SEC", "86400")))


def _ticket_create_dedup_ttl_sec() -> int:
    return max(30, int(os.getenv("QS_CHAT_TICKET_DEDUP_TTL_SEC", "180")))


def _ticket_create_cooldown_sec() -> int:
    return max(0, int(os.getenv("QS_CHAT_TICKET_CREATE_COOLDOWN_SEC", "30")))


def _last_ticket_ttl_sec() -> int:
    return max(600, int(os.getenv("QS_CHAT_LAST_TICKET_TTL_SEC", "86400")))


def _ticket_list_default_limit() -> int:
    return min(20, max(1, int(os.getenv("QS_CHAT_TICKET_LIST_LIMIT", "5"))))


def _extract_query_text(request: dict[str, Any]) -> str:
    message = request.get("message") if isinstance(request.get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""


def _extract_user_id(request: dict[str, Any]) -> str | None:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    user_id = client.get("user_id") if isinstance(client, dict) else None
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return None


def _tenant_id() -> str:
    value = os.getenv("BSL_TENANT_ID", "books").strip()
    return value or "books"


def _default_conversation_id(user_id: str) -> str:
    return f"u:{user_id}:default"


def _audit_tool_authz_decision(
    *,
    conversation_id: str,
    action_type: str,
    user_id: str,
    trace_id: str,
    request_id: str,
    path: str,
    decision: str,
    result: str,
    reason_code: str,
    status_code: int | None = None,
) -> None:
    append_action_audit(
        conversation_id=conversation_id,
        action_type=action_type,
        action_state="EXECUTED" if result == "SUCCESS" else "BLOCKED",
        decision=decision,
        result=result,
        actor_user_id=user_id,
        actor_admin_id=None,
        target_ref=path,
        auth_context={"tenant_id": _tenant_id(), "user_id": user_id},
        trace_id=trace_id,
        request_id=request_id,
        reason_code=reason_code,
        idempotency_key=None,
        metadata={"path": path, "status_code": status_code},
    )


def _extract_recent_issue_from_history(request: dict[str, Any]) -> str:
    history = request.get("history")
    if not isinstance(history, list):
        return ""
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role != "user":
            continue
        content = str(item.get("content") or "").strip()
        if len(content) < 8:
            continue
        if _is_generic_ticket_create_message(content):
            continue
        normalized = _normalize_text(content)
        if any(keyword in normalized for keyword in ["주문", "배송", "환불", "반품", "결제", "오류", "문의", "ticket"]):
            return content
    return ""


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _detect_intent(query: str) -> ToolIntent:
    q = _normalize_text(query)
    if not q:
        return ToolIntent("NONE", 0.0)

    order_ref = _extract_order_ref(query)
    ticket_no = _extract_ticket_no(query)
    has_order_ref = order_ref.order_id is not None or order_ref.order_no is not None
    has_lookup_word = any(keyword in q for keyword in ["조회", "상태", "확인", "내역", "where", "status", "lookup", "track"])

    shipment_keywords = ["배송", "택배", "출고", "shipment", "tracking"]
    refund_keywords = ["환불", "refund", "반품"]
    order_keywords = ["주문", "order", "결제", "payment"]
    ticket_list_keywords = ["문의 내역", "문의 목록", "티켓 내역", "티켓 목록", "ticket list", "my tickets", "최근 문의"]
    ticket_status_keywords = ["문의 상태", "티켓 상태", "ticket status", "ticket lookup", "내 문의"]
    ticket_create_keywords = ["문의 접수", "티켓 생성", "상담원 연결", "문의 남길", "ticket create", "support ticket"]
    cancel_keywords = ["주문 취소", "취소해", "cancel order", "cancel my order"]
    refund_create_keywords = ["환불 신청", "환불 접수", "refund request", "환불해"]
    policy_keywords = ["조건", "정리", "안내", "절차", "규정", "기준", "수수료", "policy", "guide"]
    recommendation_keywords = ["추천", "비슷한 책", "유사한 책", "related book", "similar book", "recommend"]
    has_policy_word = any(keyword in q for keyword in policy_keywords)
    has_recommend_word = any(keyword in q for keyword in recommendation_keywords)

    if any(keyword in q for keyword in cancel_keywords) and (has_order_ref or "주문" in q or "order" in q) and not has_policy_word:
        return ToolIntent("ORDER_CANCEL", 0.96)
    if any(keyword in q for keyword in refund_create_keywords) and (has_order_ref or "주문" in q or "order" in q) and not has_policy_word:
        return ToolIntent("REFUND_CREATE", 0.95)
    if has_policy_word and any(keyword in q for keyword in refund_keywords):
        return ToolIntent("REFUND_POLICY", 0.93)
    if has_policy_word and any(keyword in q for keyword in shipment_keywords):
        return ToolIntent("SHIPPING_POLICY", 0.9)
    if has_policy_word and any(keyword in q for keyword in order_keywords):
        return ToolIntent("ORDER_POLICY", 0.85)
    if any(keyword in q for keyword in ticket_list_keywords):
        return ToolIntent("TICKET_LIST", 0.95)
    if ticket_no:
        return ToolIntent("TICKET_STATUS", 0.95)
    if any(keyword in q for keyword in ticket_status_keywords):
        return ToolIntent("TICKET_STATUS", 0.95)
    if any(keyword in q for keyword in ticket_create_keywords):
        return ToolIntent("TICKET_CREATE", 0.93)
    if has_recommend_word and any(keyword in q for keyword in ["도서", "책", "book", "장바구니", "cart"]):
        if "장바구니" in q or "cart" in q:
            return ToolIntent("CART_RECOMMEND", 0.92)
        return ToolIntent("BOOK_RECOMMEND", 0.9)

    if any(keyword in q for keyword in shipment_keywords) and (has_lookup_word or has_order_ref):
        return ToolIntent("SHIPMENT_LOOKUP", 0.92)
    if any(keyword in q for keyword in refund_keywords) and (has_lookup_word or has_order_ref):
        return ToolIntent("REFUND_LOOKUP", 0.9)
    if any(keyword in q for keyword in order_keywords) and (has_lookup_word or has_order_ref):
        return ToolIntent("ORDER_LOOKUP", 0.86)
    return ToolIntent("NONE", 0.0)


def _extract_order_ref(query: str) -> OrderRef:
    if not query:
        return OrderRef(None, None)

    order_no_match = re.search(r"\bORD[0-9A-Z]+\b", query.upper())
    order_no = order_no_match.group(0) if order_no_match else None

    order_id_match = re.search(r"(?:주문번호|주문|order)\s*#?\s*(\d{1,12})", query, flags=re.IGNORECASE)
    order_id = int(order_id_match.group(1)) if order_id_match else None

    return OrderRef(order_id=order_id, order_no=order_no)


def _is_commerce_related(query: str) -> bool:
    q = _normalize_text(query)
    if not q:
        return False
    return any(keyword in q for keyword in ["주문", "배송", "환불", "결제", "order", "shipping", "refund", "payment"])


def _format_krw(amount: Any) -> str:
    try:
        value = int(amount)
    except Exception:
        value = 0
    return f"{value:,}원"


def _extract_recommendation_seed_query(query: str, *, book_slots: BookQuerySlots | None = None) -> str:
    raw = (query or "").strip()
    if not raw:
        return ""

    slots = book_slots if isinstance(book_slots, BookQuerySlots) else extract_book_query_slots(raw)
    if isinstance(slots.isbn, str) and slots.isbn:
        return slots.isbn
    if isinstance(slots.title, str) and slots.title:
        return slots.title
    if isinstance(slots.series, str) and slots.series and isinstance(slots.volume, int) and slots.volume > 0:
        return f"{slots.series} {slots.volume}권"

    quoted_patterns = [
        r"[\"'“”‘’「」『』《》〈〉]\s*([^\"'“”‘’「」『』《》〈〉]{2,120})\s*[\"'“”‘’「」『』《》〈〉]",
    ]
    for pattern in quoted_patterns:
        match = re.search(pattern, raw)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 2:
                return candidate

    match = re.search(
        r"(?:도서|책)\s*[:：]?\s*([0-9A-Za-z가-힣一-龥·\-\s]{2,120}?)(?:\s*(?:기준|관련|처럼|의|을|를|으로)|$)",
        raw,
    )
    if match:
        candidate = match.group(1).strip()
        if len(candidate) >= 2:
            return candidate

    split_tokens = ["기준으로", "기준", "관련으로", "관련", "추천해", "추천"]
    for token in split_tokens:
        if token in raw:
            candidate = raw.split(token, 1)[0].strip()
            candidate = re.sub(r"^(도서|책)\s*", "", candidate).strip()
            if len(candidate) >= 2:
                return candidate
    return ""


def _normalize_title_for_compare(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip().lower())


def _selection_state_from_db(session_id: str) -> dict[str, Any] | None:
    row = get_durable_chat_session_state(session_id)
    if not isinstance(row, dict):
        return None
    selection = row.get("selection")
    if isinstance(selection, dict):
        return selection
    return None


def _extract_reference_index(query: str) -> int | None:
    q = (query or "").strip().lower()
    if not q:
        return None

    arabic = re.search(r"(\d{1,2})\s*(?:번째|번쨰|번|th)", q)
    if arabic:
        try:
            value = int(arabic.group(1))
        except Exception:
            value = 0
        if value >= 1:
            return value

    ko_words = {
        "첫번째": 1,
        "첫째": 1,
        "두번째": 2,
        "둘째": 2,
        "세번째": 3,
        "셋째": 3,
        "네번째": 4,
        "넷째": 4,
    }
    for token, index in ko_words.items():
        if token in q:
            return index
    return None


def _looks_like_reference_query(query: str, *, has_selection_state: bool) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False

    pronoun_tokens = ["그거", "그 책", "아까 추천", "that one", "the second", "이거"]
    has_pronoun = any(token in q for token in pronoun_tokens)
    has_ordinal = _extract_reference_index(q) is not None
    if not has_pronoun and not has_ordinal:
        return False

    recommendation_tokens = ["추천", "도서", "책", "book"]
    if any(token in q for token in recommendation_tokens):
        return True
    return has_selection_state


def _looks_like_selection_followup_query(query: str) -> bool:
    q = _normalize_text(query)
    if not q:
        return False
    followup_tokens = [
        "다른 출판사",
        "다른 판본",
        "다른 버전",
        "더 쉬운",
        "쉬운 버전",
        "더 어려운",
        "어려운 버전",
        "비슷한 거",
        "유사한",
        "other publisher",
        "easier version",
        "harder version",
    ]
    return any(token in q for token in followup_tokens)


def _selection_seed_candidate(selection_state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = selection_state.get("last_candidates") if isinstance(selection_state.get("last_candidates"), list) else []
    selected_book = selection_state.get("selected_book") if isinstance(selection_state.get("selected_book"), dict) else None
    selected_index = selection_state.get("selected_index")
    if isinstance(selected_book, dict) and str(selected_book.get("title") or "").strip():
        return selected_book
    if isinstance(selected_index, int) and selected_index > 0:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if int(candidate.get("index") or 0) == selected_index:
                return candidate
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("title") or "").strip():
            return candidate
    return None


def _build_selection_candidates(candidates: list[dict[str, Any]], *, max_items: int = 5) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates[:max_items], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        raw_isbn = str(item.get("isbn") or "").strip()
        series = str(item.get("series") or item.get("series_title") or "").strip()
        raw_format = str(item.get("format") or item.get("book_format") or item.get("media_type") or "").strip().lower()
        if raw_format in {"ebook", "e-book", "electronic", "전자책"}:
            normalized_format = "ebook"
        elif raw_format in {"print", "paperback", "hardcover", "종이책", "양장", "무선"}:
            normalized_format = "print"
        else:
            normalized_format = None
        volume_value = item.get("volume")
        if volume_value is None:
            volume_value = item.get("series_no")
        normalized_volume: int | None = None
        if isinstance(volume_value, (int, float, str)):
            try:
                parsed_volume = int(str(volume_value).strip())
            except Exception:
                parsed_volume = 0
            if parsed_volume > 0:
                normalized_volume = parsed_volume
        built.append(
            {
                "index": idx,
                "doc_id": str(item.get("doc_id") or "").strip(),
                "title": title,
                "author": str(item.get("author") or "").strip(),
                "isbn": normalize_isbn(raw_isbn) or raw_isbn,
                "series": series or None,
                "volume": normalized_volume,
                "format": normalized_format,
            }
        )
    return built


def _save_selection_state(
    session_id: str,
    *,
    user_id: str | None,
    trace_id: str,
    request_id: str,
    candidates: list[dict[str, Any]],
    selected_index: int | None = None,
) -> None:
    selection_payload: dict[str, Any] = {
        "type": "BOOK_RECOMMENDATION",
        "updated_at": int(time.time()),
        "last_candidates": candidates,
        "selected_index": selected_index,
        "selected_book": None,
    }
    if selected_index is not None:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if int(candidate.get("index") or 0) == selected_index:
                selection_payload["selected_book"] = candidate
                break
    upsert_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        selection=selection_payload,
        last_turn_id=request_id,
        idempotency_key=request_id,
    )


def _resolve_selection_reference(query: str, selection_state: dict[str, Any]) -> tuple[dict[str, Any] | None, int | None]:
    candidates = selection_state.get("last_candidates") if isinstance(selection_state.get("last_candidates"), list) else []
    selected_book = selection_state.get("selected_book") if isinstance(selection_state.get("selected_book"), dict) else None
    selected_index = selection_state.get("selected_index")
    if isinstance(selected_index, int) and selected_index <= 0:
        selected_index = None

    if not candidates:
        return None, None

    explicit_index = _extract_reference_index(query)
    if explicit_index is not None:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if int(candidate.get("index") or 0) == explicit_index:
                return candidate, explicit_index
        return None, explicit_index

    if selected_book is not None and isinstance(selected_index, int):
        return selected_book, selected_index
    if len(candidates) == 1 and isinstance(candidates[0], dict):
        only = candidates[0]
        return only, int(only.get("index") or 1)
    return None, None


def _render_selection_options(selection_state: dict[str, Any], *, max_items: int = 3) -> str:
    candidates = selection_state.get("last_candidates") if isinstance(selection_state.get("last_candidates"), list) else []
    lines: list[str] = []
    for item in candidates[:max_items]:
        if not isinstance(item, dict):
            continue
        index = int(item.get("index") or 0)
        title = str(item.get("title") or "").strip()
        author = str(item.get("author") or "").strip()
        isbn = str(item.get("isbn") or "").strip()
        volume = item.get("volume")
        if index <= 0 or not title:
            continue
        meta_parts: list[str] = []
        if author:
            meta_parts.append(author)
        if isinstance(volume, int) and volume > 0:
            meta_parts.append(f"{volume}권")
        if isbn:
            meta_parts.append(f"ISBN {isbn}")
        meta = f" ({' / '.join(meta_parts)})" if meta_parts else ""
        lines.append(f"{index}) {title}{meta}")
    if not lines:
        return "선택 가능한 추천 목록이 없습니다. 다시 추천해달라고 요청해 주세요."
    return "어떤 후보를 말하시는지 번호로 선택해 주세요.\n" + "\n".join(lines)


def _render_selected_candidate(candidate: dict[str, Any], selected_index: int) -> str:
    title = str(candidate.get("title") or "").strip()
    author = str(candidate.get("author") or "").strip()
    doc_id = str(candidate.get("doc_id") or "").strip()
    isbn = str(candidate.get("isbn") or "").strip()
    volume = candidate.get("volume")
    book_format = str(candidate.get("format") or "").strip().lower()
    parts: list[str] = []
    if author:
        parts.append(f"저자 {author}")
    if isbn:
        parts.append(f"ISBN {isbn}")
    if isinstance(volume, int) and volume > 0:
        parts.append(f"{volume}권")
    if book_format in {"ebook", "print"}:
        parts.append("전자책" if book_format == "ebook" else "종이책")
    if doc_id:
        parts.append(f"ID {doc_id}")
    suffix = f" ({', '.join(parts)})" if parts else ""
    return (
        f"{selected_index}번째로 선택하신 도서는 '{title}'{suffix}입니다.\n"
        "이 책 기준으로 비슷한 도서를 다시 추천해드릴까요?"
    )


def _pick_cart_seed_titles(cart_items: list[dict[str, Any]], limit: int = 2) -> list[str]:
    seeds: list[str] = []
    for item in cart_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        normalized = _normalize_title_for_compare(title)
        if not normalized:
            continue
        if any(_normalize_title_for_compare(existing) == normalized for existing in seeds):
            continue
        seeds.append(title)
        if len(seeds) >= limit:
            break
    return seeds


def _order_status_ko(status: str | None) -> str:
    mapping = {
        "CREATED": "주문 접수",
        "PAYMENT_PENDING": "결제 대기",
        "PAID": "결제 완료",
        "READY_TO_SHIP": "배송 준비",
        "SHIPPED": "배송 중",
        "DELIVERED": "배송 완료",
        "PARTIALLY_REFUNDED": "부분 환불",
        "REFUNDED": "환불 완료",
        "CANCELED": "주문 취소",
    }
    if not status:
        return "상태 미정"
    return mapping.get(status, status)


def _shipment_status_ko(status: str | None) -> str:
    mapping = {
        "READY": "출고 준비",
        "SHIPPED": "배송 중",
        "DELIVERED": "배송 완료",
        "CANCELED": "배송 취소",
    }
    if not status:
        return "배송 정보 없음"
    return mapping.get(status, status)


def _refund_status_ko(status: str | None) -> str:
    mapping = {
        "REQUESTED": "환불 접수",
        "APPROVED": "환불 승인",
        "PROCESSING": "환불 처리 중",
        "REFUNDED": "환불 완료",
        "FAILED": "환불 실패",
        "REJECTED": "환불 거절",
    }
    if not status:
        return "환불 정보 없음"
    return mapping.get(status, status)


def _build_tool_source(tool_name: str, endpoint: str, snippet: str) -> tuple[list[dict[str, Any]], list[str]]:
    timestamp = datetime.now(UTC).isoformat()
    citation_key = f"tool:{tool_name}:{int(time.time())}"
    source = {
        "citation_key": citation_key,
        "doc_id": f"tool:{tool_name}",
        "chunk_id": citation_key,
        "title": f"{tool_name} 실시간 조회",
        "url": endpoint,
        "snippet": f"{snippet} (조회시각: {timestamp})",
    }
    return [source], [citation_key]


def _policy_topic_cache_key(topic: str) -> str:
    normalized_topic = str(topic or "").strip().lower() or "generic"
    return f"chat:policy-topic:{_tenant_id()}:{normalized_topic}"


def _build_cached_policy_response(
    *,
    topic: str,
    trace_id: str,
    request_id: str,
    tool_name: str,
    endpoint: str,
    content_builder: Callable[[], tuple[str, str]],
) -> dict[str, Any]:
    cache_key = _policy_topic_cache_key(topic)
    cached = _CACHE.get_json(cache_key)
    if isinstance(cached, dict):
        cached_content = str(cached.get("content") or "").strip()
        cached_snippet = str(cached.get("source_snippet") or "").strip()
        if cached_content and cached_snippet:
            metrics.inc("chat_policy_topic_cache_total", {"topic": topic, "result": "hit"})
            return _build_response(
                trace_id,
                request_id,
                "ok",
                cached_content,
                tool_name=tool_name,
                endpoint=endpoint,
                source_snippet=cached_snippet,
            )

    content, source_snippet = content_builder()
    metrics.inc("chat_policy_topic_cache_total", {"topic": topic, "result": "miss"})
    _CACHE.set_json(
        cache_key,
        {"content": content, "source_snippet": source_snippet},
        ttl=_policy_topic_cache_ttl_sec(),
    )
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name=tool_name,
        endpoint=endpoint,
        source_snippet=source_snippet,
    )


def _contains_success_claim(content: str) -> bool:
    normalized = _normalize_text(content)
    if not normalized:
        return False
    patterns = [
        "조회가 완료",
        "조회 완료",
        "취소가 완료",
        "환불 접수가 완료",
        "접수가 완료",
        "실행이 완료",
    ]
    return any(pattern in normalized for pattern in patterns)


def _claim_repair_response(base: dict[str, Any], reason_code: str) -> dict[str, Any]:
    repaired = dict(base)
    if reason_code == "DENY_CLAIM:NOT_CONFIRMED":
        repaired["status"] = "pending_confirmation"
        repaired["reason_code"] = reason_code
        repaired["recoverable"] = True
        repaired["next_action"] = "CONFIRM_ACTION"
        repaired["retry_after_ms"] = None
        repaired["answer"] = {
            "role": "assistant",
            "content": "확인 절차가 끝나지 않아 완료를 안내할 수 없습니다. 확인 코드를 입력해 주세요.",
        }
        return repaired
    repaired["status"] = "tool_fallback"
    repaired["reason_code"] = reason_code
    repaired["recoverable"] = True
    repaired["next_action"] = "RETRY"
    repaired["retry_after_ms"] = 3000
    repaired["answer"] = {
        "role": "assistant",
        "content": "실행/조회 근거를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    }
    return repaired


def _apply_claim_verifier(base: dict[str, Any]) -> dict[str, Any]:
    status = str(base.get("status") or "")
    reason_code = str(base.get("reason_code") or "")
    answer = base.get("answer") if isinstance(base.get("answer"), dict) else {}
    content = str(answer.get("content") or "")
    has_success_claim = _contains_success_claim(content)
    if not has_success_claim:
        return base

    if reason_code in {"CONFIRMATION_REQUIRED", "DENY_EXECUTE:NOT_CONFIRMED"}:
        metrics.inc("chat_claim_block_total", {"reason": "DENY_CLAIM:NOT_CONFIRMED"})
        metrics.inc("chat_claim_repair_total", {"reason": "DENY_CLAIM:NOT_CONFIRMED"})
        return _claim_repair_response(base, "DENY_CLAIM:NOT_CONFIRMED")

    sources = base.get("sources") if isinstance(base.get("sources"), list) else []
    citations = base.get("citations") if isinstance(base.get("citations"), list) else []
    if status == "ok" and (not sources or not citations):
        metrics.inc("chat_claim_block_total", {"reason": "DENY_CLAIM:NO_TOOL_RESULT"})
        metrics.inc("chat_claim_repair_total", {"reason": "DENY_CLAIM:NO_TOOL_RESULT"})
        return _claim_repair_response(base, "DENY_CLAIM:NO_TOOL_RESULT")
    return base


def _build_response(
    trace_id: str,
    request_id: str,
    status: str,
    content: str,
    *,
    tool_name: str | None = None,
    endpoint: str | None = None,
    source_snippet: str | None = None,
    reason_code: str | None = None,
    recoverable: bool | None = None,
    retry_after_ms: int | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    status_defaults: dict[str, dict[str, Any]] = {
        "ok": {"reason_code": "OK", "recoverable": False, "next_action": "NONE", "retry_after_ms": None},
        "needs_auth": {"reason_code": "AUTH_REQUIRED", "recoverable": True, "next_action": "LOGIN_REQUIRED", "retry_after_ms": None},
        "needs_input": {"reason_code": "MISSING_INPUT", "recoverable": True, "next_action": "PROVIDE_REQUIRED_INFO", "retry_after_ms": None},
        "pending_confirmation": {"reason_code": "CONFIRMATION_REQUIRED", "recoverable": True, "next_action": "CONFIRM_ACTION", "retry_after_ms": None},
        "tool_fallback": {"reason_code": "TOOL_UNAVAILABLE", "recoverable": True, "next_action": "RETRY", "retry_after_ms": 3000},
        "not_found": {"reason_code": "RESOURCE_NOT_FOUND", "recoverable": True, "next_action": "PROVIDE_REQUIRED_INFO", "retry_after_ms": None},
        "forbidden": {"reason_code": "AUTH_FORBIDDEN", "recoverable": False, "next_action": "OPEN_SUPPORT_TICKET", "retry_after_ms": None},
        "expired": {"reason_code": "CONFIRMATION_EXPIRED", "recoverable": True, "next_action": "RETRY", "retry_after_ms": None},
        "aborted": {"reason_code": "USER_ABORTED", "recoverable": True, "next_action": "NONE", "retry_after_ms": None},
        "invalid_state": {"reason_code": "INVALID_WORKFLOW_STATE", "recoverable": True, "next_action": "OPEN_SUPPORT_TICKET", "retry_after_ms": None},
        "unsupported": {"reason_code": "UNSUPPORTED_WORKFLOW", "recoverable": False, "next_action": "OPEN_SUPPORT_TICKET", "retry_after_ms": None},
    }
    defaults = status_defaults.get(status, {"reason_code": "UNKNOWN", "recoverable": True, "next_action": "RETRY", "retry_after_ms": 3000})
    sources: list[dict[str, Any]] = []
    citations: list[str] = []
    if tool_name and endpoint and source_snippet:
        sources, citations = _build_tool_source(tool_name, endpoint, source_snippet)
    resolved_reason_code = reason_code if isinstance(reason_code, str) and reason_code.strip() else defaults["reason_code"]
    resolved_recoverable = bool(defaults["recoverable"] if recoverable is None else recoverable)
    resolved_next_action = next_action if isinstance(next_action, str) and next_action.strip() else defaults["next_action"]
    resolved_retry_after_ms = defaults["retry_after_ms"] if retry_after_ms is None else retry_after_ms
    metrics.inc(
        "chat_error_recovery_hint_total",
        {
            "next_action": resolved_next_action,
            "reason_code": resolved_reason_code,
            "source": "tool",
        },
    )
    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": status,
        "reason_code": resolved_reason_code,
        "recoverable": resolved_recoverable,
        "next_action": resolved_next_action,
        "retry_after_ms": resolved_retry_after_ms,
        "answer": {"role": "assistant", "content": content},
        "sources": sources,
        "citations": citations,
    }
    return _apply_claim_verifier(response)


def _resolve_session_id(request: dict[str, Any], user_id: str | None) -> str:
    session_id = request.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    if user_id:
        return f"u:{user_id}:default"
    return "anon:default"


def _policy_route_result(route: str) -> str:
    if route in {ROUTE_ASK, ROUTE_OPTIONS}:
        return "BLOCKED"
    return "SUCCESS"


def _record_policy_decision(
    *,
    session_id: str,
    user_id: str | None,
    trace_id: str,
    request_id: str,
    intent: str,
    decision: PolicyDecision,
) -> None:
    normalized_intent = str(intent or "NONE").upper()
    metrics.inc("chat_route_total", {"route": decision.route, "intent": normalized_intent})
    if decision.route in {ROUTE_ASK, ROUTE_OPTIONS}:
        metrics.inc("chat_policy_block_total", {"reason_code": decision.reason_code})
    append_action_audit(
        conversation_id=session_id,
        action_type="POLICY_DECISION",
        action_state=decision.route,
        decision="ALLOW" if decision.route not in {ROUTE_ASK, ROUTE_OPTIONS} else "DENY",
        result=_policy_route_result(decision.route),
        actor_user_id=user_id,
        actor_admin_id=None,
        target_ref=normalized_intent,
        auth_context={"tenant_id": _tenant_id(), "user_id": user_id},
        trace_id=trace_id,
        request_id=request_id,
        reason_code=decision.reason_code,
        idempotency_key=f"policy:{session_id}:{request_id}",
        metadata={
            "policy_rule_id": decision.policy_rule_id,
            "missing_slots": decision.missing_slots,
            "decision_snapshot": decision.decision_snapshot,
        },
    )
    upsert_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        summary_short=f"route={decision.route}|reason={decision.reason_code}|rule={decision.policy_rule_id}",
        last_turn_id=request_id,
        idempotency_key=request_id,
    )


def _workflow_cache_key(session_id: str) -> str:
    return f"chat:workflow:{session_id}"


def _workflow_action_receipt_cache_key(idempotency_key: str) -> str:
    return f"chat:workflow:receipt:{idempotency_key}"


def _workflow_fsm_state(workflow: dict[str, Any] | None) -> str:
    if not isinstance(workflow, dict):
        return "INIT"
    raw = str(workflow.get("fsm_state") or "").strip().upper()
    if raw:
        return raw
    legacy_step = str(workflow.get("step") or "").strip().lower()
    if legacy_step == "awaiting_confirmation":
        return "AWAITING_CONFIRMATION"
    if legacy_step == "executed":
        return "EXECUTED"
    return "INIT"


def _workflow_step_from_fsm(state: str) -> str:
    mapping = {
        "INIT": "init",
        "AWAITING_CONFIRMATION": "awaiting_confirmation",
        "CONFIRMED": "confirmed",
        "EXECUTING": "executing",
        "EXECUTED": "executed",
        "ABORTED": "aborted",
        "EXPIRED": "expired",
        "FAILED_RETRYABLE": "failed_retryable",
        "FAILED_FINAL": "failed_final",
    }
    return mapping.get(str(state or "").upper(), "init")


def _apply_workflow_transition(
    workflow: dict[str, Any],
    *,
    to_state: str,
    session_id: str,
    user_id: str,
    trace_id: str,
    request_id: str,
    reason_code: str,
    persist: bool = True,
    metadata: dict[str, Any] | None = None,
) -> bool:
    current_state = _workflow_fsm_state(workflow)
    normalized_to = str(to_state or "").strip().upper()
    allowed = _WORKFLOW_ALLOWED_TRANSITIONS.get(current_state, set())
    if normalized_to != current_state and normalized_to not in allowed:
        metrics.inc("chat_execute_block_total", {"reason": "invalid_transition"})
        append_action_audit(
            conversation_id=session_id,
            action_type=str(workflow.get("workflow_type") or "WORKFLOW"),
            action_state=current_state,
            decision="DENY",
            result="BLOCKED",
            actor_user_id=user_id,
            actor_admin_id=None,
            target_ref=str(workflow.get("order_no") or workflow.get("workflow_id") or session_id),
            auth_context={"tenant_id": _tenant_id(), "user_id": user_id},
            trace_id=trace_id,
            request_id=request_id,
            reason_code="INVALID_WORKFLOW_TRANSITION",
            idempotency_key=str((workflow.get("action_draft") or {}).get("idempotency_key") or None),
            metadata={
                "from_state": current_state,
                "to_state": normalized_to,
                "workflow_type": workflow.get("workflow_type"),
            },
        )
        return False

    workflow["fsm_state"] = normalized_to
    workflow["step"] = _workflow_step_from_fsm(normalized_to)
    workflow["updated_at"] = int(time.time())
    transition_history = workflow.get("transition_history")
    if not isinstance(transition_history, list):
        transition_history = []
    transition_history.append(
        {
            "from": current_state,
            "to": normalized_to,
            "reason_code": reason_code,
            "request_id": request_id,
            "updated_at": int(time.time()),
        }
    )
    workflow["transition_history"] = transition_history[-20:]
    metrics.inc("chat_confirm_fsm_transition_total", {"from": current_state, "to": normalized_to})
    if persist:
        _save_workflow(session_id, workflow, ttl_sec=_workflow_ttl_sec())

    append_action_audit(
        conversation_id=session_id,
        action_type=str(workflow.get("workflow_type") or "WORKFLOW"),
        action_state=normalized_to,
        decision="ALLOW" if normalized_to not in {"ABORTED", "EXPIRED", "FAILED_FINAL"} else "DENY",
        result="SUCCESS" if normalized_to == "EXECUTED" else "IN_PROGRESS",
        actor_user_id=user_id,
        actor_admin_id=None,
        target_ref=str(workflow.get("order_no") or workflow.get("workflow_id") or session_id),
        auth_context={"tenant_id": _tenant_id(), "user_id": user_id},
        trace_id=trace_id,
        request_id=request_id,
        reason_code=reason_code,
        idempotency_key=str((workflow.get("action_draft") or {}).get("idempotency_key") or None),
        metadata={
            "from_state": current_state,
            "to_state": normalized_to,
            "workflow_type": workflow.get("workflow_type"),
            **(metadata or {}),
        },
    )
    return True


def _build_confirmation_token(trace_id: str, request_id: str, session_id: str) -> str:
    seed = f"{trace_id}:{request_id}:{session_id}:{time.time_ns()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()
    return digest[:6]


def _save_workflow(session_id: str, workflow: dict[str, Any], ttl_sec: int) -> None:
    _CACHE.set_json(_workflow_cache_key(session_id), workflow, ttl=max(1, ttl_sec))


def _load_workflow(session_id: str) -> dict[str, Any] | None:
    cached = _CACHE.get_json(_workflow_cache_key(session_id))
    if isinstance(cached, dict):
        return cached
    return None


def _clear_workflow(session_id: str) -> None:
    _CACHE.set_json(_workflow_cache_key(session_id), {"state": "cleared", "fsm_state": "CLEARED"}, ttl=1)


def _last_ticket_cache_key(session_id: str) -> str:
    return f"chat:last-ticket:{session_id}"


def _last_ticket_user_cache_key(user_id: str) -> str:
    return f"chat:last-ticket:user:{user_id}"


def _user_id_from_session_id(session_id: str) -> str | None:
    if not session_id:
        return None
    match = re.match(r"^u:([^:]+)(?::|$)", session_id)
    if match:
        user_id = match.group(1).strip()
        if user_id:
            return user_id
    return None


def _save_last_ticket_no(session_id: str, user_id: str, ticket_no: str) -> None:
    if ticket_no:
        payload = {"ticket_no": ticket_no, "user_id": user_id}
        ttl = _last_ticket_ttl_sec()
        _CACHE.set_json(_last_ticket_cache_key(session_id), payload, ttl=ttl)
        _CACHE.set_json(_last_ticket_user_cache_key(user_id), {"ticket_no": ticket_no}, ttl=ttl)


def _load_last_ticket_no(session_id: str, user_id: str) -> str | None:
    session_cached = _CACHE.get_json(_last_ticket_cache_key(session_id))
    if isinstance(session_cached, dict):
        owner = str(session_cached.get("user_id") or "").strip()
        value = session_cached.get("ticket_no")
        if owner == user_id and isinstance(value, str) and value.strip():
            return value.strip()
        if owner and owner != user_id:
            metrics.inc("chat_ticket_session_cache_owner_mismatch_total", {"cache": "last_ticket"})

    user_cached = _CACHE.get_json(_last_ticket_user_cache_key(user_id))
    if isinstance(user_cached, dict):
        value = user_cached.get("ticket_no")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _unresolved_context_cache_key(session_id: str) -> str:
    return f"chat:unresolved:{session_id}"


def _load_unresolved_context(session_id: str) -> dict[str, Any] | None:
    cached = _CACHE.get_json(_unresolved_context_cache_key(session_id))
    if isinstance(cached, dict):
        if cached.get("cleared") is True:
            return None
        return cached
    return None


def _clear_unresolved_context(session_id: str) -> None:
    _CACHE.set_json(_unresolved_context_cache_key(session_id), {"cleared": True}, ttl=1)


def _fallback_counter_cache_key(session_id: str) -> str:
    return f"chat:fallback:count:{session_id}"


def _reset_fallback_counter(session_id: str) -> None:
    _CACHE.set_json(_fallback_counter_cache_key(session_id), {"count": 0}, ttl=5)


def _ticket_create_fingerprint(user_id: str, query: str) -> str:
    normalized = _normalize_text(query)
    return hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()[:24]


def _ticket_create_dedup_epoch_key(session_id: str) -> str:
    return f"chat:ticket-create:dedup:epoch:{session_id}"


def _ticket_create_dedup_user_epoch_key(user_id: str) -> str:
    return f"chat:ticket-create:dedup:user-epoch:{user_id}"


def _ticket_create_dedup_epoch(session_id: str) -> int:
    cached = _CACHE.get_json(_ticket_create_dedup_epoch_key(session_id))
    if isinstance(cached, dict):
        raw_epoch = cached.get("epoch")
        if isinstance(raw_epoch, int) and raw_epoch >= 0:
            return raw_epoch
    return 0


def _bump_ticket_create_dedup_epoch(session_id: str) -> int:
    next_epoch = _ticket_create_dedup_epoch(session_id) + 1
    _CACHE.set_json(
        _ticket_create_dedup_epoch_key(session_id),
        {"epoch": next_epoch},
        ttl=max(600, _ticket_create_dedup_ttl_sec() * 4),
    )
    return next_epoch


def _ticket_create_dedup_user_epoch(user_id: str) -> int:
    cached = _CACHE.get_json(_ticket_create_dedup_user_epoch_key(user_id))
    if isinstance(cached, dict):
        raw_epoch = cached.get("epoch")
        if isinstance(raw_epoch, int) and raw_epoch >= 0:
            return raw_epoch
    return 0


def _bump_ticket_create_dedup_user_epoch(user_id: str) -> int:
    next_epoch = _ticket_create_dedup_user_epoch(user_id) + 1
    _CACHE.set_json(
        _ticket_create_dedup_user_epoch_key(user_id),
        {"epoch": next_epoch},
        ttl=max(600, _ticket_create_dedup_ttl_sec() * 4),
    )
    return next_epoch


def _ticket_create_dedup_cache_key(session_id: str, fingerprint: str) -> str:
    epoch = _ticket_create_dedup_epoch(session_id)
    return f"chat:ticket-create:dedup:{session_id}:e{epoch}:{fingerprint}"


def _ticket_create_dedup_user_cache_key(user_id: str, fingerprint: str) -> str:
    epoch = _ticket_create_dedup_user_epoch(user_id)
    return f"chat:ticket-create:dedup:user:{user_id}:e{epoch}:{fingerprint}"


def _ticket_create_last_cache_key(session_id: str) -> str:
    return f"chat:ticket-create:last:{session_id}"


def _ticket_create_last_user_cache_key(user_id: str) -> str:
    return f"chat:ticket-create:last:user:{user_id}"


def _load_ticket_create_dedup(session_id: str, user_id: str, fingerprint: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates = (
        ("session", _CACHE.get_json(_ticket_create_dedup_cache_key(session_id, fingerprint))),
        ("user", _CACHE.get_json(_ticket_create_dedup_user_cache_key(user_id, fingerprint))),
    )
    best_payload: dict[str, Any] | None = None
    best_scope: str | None = None
    best_ts = -1
    for scope, cached in candidates:
        if not isinstance(cached, dict):
            continue
        cached_ts = cached.get("cached_at")
        ts = int(cached_ts) if isinstance(cached_ts, int) else 0
        if ts > best_ts:
            best_payload = cached
            best_scope = scope
            best_ts = ts
    return best_payload, best_scope


def _save_ticket_create_dedup(session_id: str, user_id: str, fingerprint: str, payload: dict[str, Any]) -> None:
    ttl = _ticket_create_dedup_ttl_sec()
    payload_with_meta = dict(payload)
    payload_with_meta["cached_at"] = int(time.time())
    _CACHE.set_json(
        _ticket_create_dedup_cache_key(session_id, fingerprint),
        payload_with_meta,
        ttl=ttl,
    )
    _CACHE.set_json(
        _ticket_create_dedup_user_cache_key(user_id, fingerprint),
        payload_with_meta,
        ttl=ttl,
    )


def _load_ticket_create_last(session_id: str, user_id: str) -> int | None:
    timestamps: list[int] = []
    session_cached = _CACHE.get_json(_ticket_create_last_cache_key(session_id))
    if isinstance(session_cached, dict):
        owner = str(session_cached.get("user_id") or "").strip()
        raw_ts = session_cached.get("created_at")
        if owner == user_id and isinstance(raw_ts, int) and raw_ts > 0:
            timestamps.append(raw_ts)
        if owner and owner != user_id:
            metrics.inc("chat_ticket_session_cache_owner_mismatch_total", {"cache": "create_last"})

    user_cached = _CACHE.get_json(_ticket_create_last_user_cache_key(user_id))
    if isinstance(user_cached, dict):
        raw_ts = user_cached.get("created_at")
        if isinstance(raw_ts, int) and raw_ts > 0:
            timestamps.append(raw_ts)

    if timestamps:
        return max(timestamps)
    return None


def _save_ticket_create_last(session_id: str, user_id: str) -> None:
    cooldown = _ticket_create_cooldown_sec()
    ttl = max(60, cooldown * 2 if cooldown > 0 else 60)
    now_ts = int(time.time())
    payload = {"created_at": now_ts, "user_id": user_id}
    _CACHE.set_json(_ticket_create_last_cache_key(session_id), payload, ttl=ttl)
    _CACHE.set_json(_ticket_create_last_user_cache_key(user_id), {"created_at": now_ts}, ttl=ttl)


def reset_ticket_session_context(session_id: str) -> None:
    if not session_id:
        return
    _CACHE.set_json(_last_ticket_cache_key(session_id), {"cleared": True}, ttl=1)
    _CACHE.set_json(_ticket_create_last_cache_key(session_id), {"cleared": True}, ttl=1)
    user_id = _user_id_from_session_id(session_id)
    scope = "session_only"
    if user_id:
        _CACHE.set_json(_last_ticket_user_cache_key(user_id), {"cleared": True}, ttl=1)
        _CACHE.set_json(_ticket_create_last_user_cache_key(user_id), {"cleared": True}, ttl=1)
        _bump_ticket_create_dedup_user_epoch(user_id)
        scope = "session_and_user"
    _bump_ticket_create_dedup_epoch(session_id)
    metrics.inc("chat_ticket_context_reset_total", {"reason": "session_reset"})
    metrics.inc("chat_ticket_context_reset_scope_total", {"scope": scope})


def _is_generic_ticket_create_message(query: str) -> bool:
    q = _normalize_text(query)
    if not q:
        return False
    generic_phrases = [
        "문의 접수",
        "문의해줘",
        "문의 남겨줘",
        "티켓 생성",
        "상담원 연결",
        "상담 전환",
        "support ticket",
        "create ticket",
    ]
    if q in generic_phrases:
        return True
    for phrase in generic_phrases:
        if not q.startswith(phrase):
            continue
        remainder = q[len(phrase) :].strip()
        if remainder in {"", "해줘", "해주세요", "해 줘", "please"}:
            return True
    return False


def _is_confirmation_message(query: str) -> bool:
    q = _normalize_text(query)
    return any(keyword in q for keyword in ["확인", "동의", "진행", "승인", "yes", "confirm"])


def _is_abort_message(query: str) -> bool:
    q = _normalize_text(query)
    return any(keyword in q for keyword in ["요청 취소", "중단", "그만", "abort", "stop"])


def _extract_confirmation_token(query: str) -> str | None:
    if not query:
        return None
    token_match = re.search(r"\b([A-F0-9]{6})\b", query.upper())
    if token_match:
        return token_match.group(1)
    return None


def _extract_ticket_no(query: str) -> str | None:
    if not query:
        return None
    match = re.search(r"\b(STK[0-9A-Z]+)\b", query.upper())
    if match:
        return match.group(1)
    return None


def _extract_ticket_list_limit(query: str) -> int:
    default_limit = _ticket_list_default_limit()
    if not query:
        return default_limit
    match = re.search(r"(\d{1,2})\s*(?:건|개|tickets?|items?)", query, flags=re.IGNORECASE)
    if not match:
        return default_limit
    try:
        parsed = int(match.group(1))
    except Exception:
        return default_limit
    return min(20, max(1, parsed))


def _ticket_status_ko(status: str | None) -> str:
    mapping = {
        "RECEIVED": "접수 완료",
        "IN_PROGRESS": "처리 중",
        "WAITING_USER": "사용자 확인 필요",
        "RESOLVED": "해결 완료",
        "CLOSED": "종료",
    }
    if not status:
        return "상태 미정"
    return mapping.get(status, status)


def _ticket_followup_message(status: str | None) -> str:
    normalized = (status or "").upper()
    mapping = {
        "RECEIVED": "접수된 순서대로 확인 중입니다. 추가 정보가 있으면 채팅으로 남겨 주세요.",
        "IN_PROGRESS": "담당자가 확인 중입니다. 처리 완료 시 즉시 안내드리겠습니다.",
        "WAITING_USER": "추가 정보가 필요합니다. 주문번호/증상 내용을 더 남겨 주세요.",
        "RESOLVED": "처리가 완료되었습니다. 동일 문제가 재발하면 티켓번호와 함께 말씀해 주세요.",
        "CLOSED": "티켓이 종료되었습니다. 새 문의가 필요하면 다시 접수해 주세요.",
    }
    return mapping.get(normalized, "현재 티켓 상태를 확인했습니다.")


def _ticket_event_type_ko(event_type: str | None) -> str:
    mapping = {
        "TICKET_RECEIVED": "문의 접수",
        "STATUS_CHANGED": "상태 변경",
    }
    if not event_type:
        return "처리 이력"
    return mapping.get(str(event_type).upper(), str(event_type))


def _format_event_timestamp(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    normalized = text.replace("T", " ")
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    if len(normalized) >= 16:
        return normalized[:16]
    return normalized


def _ticket_category_ko(category: str | None) -> str:
    mapping = {
        "ORDER": "주문/결제",
        "SHIPPING": "배송",
        "REFUND": "환불/반품",
        "GENERAL": "일반 문의",
    }
    if not category:
        return "미분류"
    return mapping.get(str(category).upper(), str(category))


def _ticket_severity_ko(severity: str | None) -> str:
    mapping = {
        "LOW": "일반",
        "MEDIUM": "보통",
        "HIGH": "긴급",
    }
    if not severity:
        return "미지정"
    return mapping.get(str(severity).upper(), str(severity))


def _infer_ticket_category(query: str) -> str:
    q = _normalize_text(query)
    if any(keyword in q for keyword in ["환불", "반품", "refund"]):
        return "REFUND"
    if any(keyword in q for keyword in ["배송", "택배", "shipment", "tracking"]):
        return "SHIPPING"
    if any(keyword in q for keyword in ["주문", "결제", "order", "payment"]):
        return "ORDER"
    return "GENERAL"


def _infer_ticket_severity(query: str) -> str:
    q = _normalize_text(query)
    if any(keyword in q for keyword in ["긴급", "critical", "결제 실패", "오류", "에러", "실패"]):
        return "HIGH"
    if any(keyword in q for keyword in ["불편", "지연", "delay"]):
        return "MEDIUM"
    return "LOW"


def _record_tool_metrics(intent: str, tool: str, result: str) -> None:
    metrics.inc("chat_tool_route_total", {"intent": intent, "tool": tool, "status": result})


def _tool_circuit_open_key(tool_name: str) -> str:
    return f"chat:tool:circuit:open:{tool_name}"


def _tool_circuit_fail_key(tool_name: str) -> str:
    return f"chat:tool:circuit:fail:{tool_name}"


def _is_tool_circuit_open(tool_name: str) -> bool:
    cached = _CACHE.get_json(_tool_circuit_open_key(tool_name))
    if not isinstance(cached, dict):
        return False
    opened_until = int(cached.get("opened_until") or 0)
    now = int(time.time())
    return opened_until > now


def _record_tool_failure(tool_name: str) -> None:
    fail_key = _tool_circuit_fail_key(tool_name)
    cached = _CACHE.get_json(fail_key)
    fail_count = 0
    if isinstance(cached, dict):
        fail_count = int(cached.get("count") or 0)
    fail_count += 1
    _CACHE.set_json(fail_key, {"count": fail_count}, ttl=max(5, _tool_circuit_open_sec() * 2))
    if fail_count >= _tool_circuit_fail_threshold():
        opened_until = int(time.time()) + _tool_circuit_open_sec()
        _CACHE.set_json(_tool_circuit_open_key(tool_name), {"opened_until": opened_until}, ttl=_tool_circuit_open_sec())
        metrics.inc("chat_circuit_breaker_state", {"tool": tool_name, "state": "open"})


def _record_tool_success(tool_name: str) -> None:
    _CACHE.set_json(_tool_circuit_fail_key(tool_name), {"count": 0}, ttl=1)
    _CACHE.set_json(_tool_circuit_open_key(tool_name), {"opened_until": 0}, ttl=1)
    metrics.inc("chat_circuit_breaker_state", {"tool": tool_name, "state": "closed"})


async def _call_commerce(
    method: str,
    path: str,
    *,
    user_id: str,
    session_id: str | None = None,
    trace_id: str,
    request_id: str,
    payload: dict[str, Any] | None = None,
    tool_name: str,
    intent: str,
) -> dict[str, Any]:
    tenant_id = _tenant_id()
    conversation_id = session_id or _default_conversation_id(user_id)
    if not user_id or not tenant_id:
        metrics.inc("chat_authz_check_total", {"result": "deny", "action": intent, "reason": "missing_context"})
        _audit_tool_authz_decision(
            conversation_id=conversation_id,
            action_type=tool_name,
            user_id=user_id or "unknown",
            trace_id=trace_id,
            request_id=request_id,
            path=path,
            decision="DENY",
            result="BLOCKED",
            reason_code="AUTH_CONTEXT_MISSING",
            status_code=400,
        )
        raise ToolCallError("auth_context_missing", "인증 컨텍스트가 누락되어 요청을 처리할 수 없습니다.", status_code=400)
    metrics.inc("chat_authz_check_total", {"result": "allow", "action": intent, "reason": "context_ok"})
    if _is_tool_circuit_open(tool_name):
        metrics.inc("chat_circuit_breaker_state", {"tool": tool_name, "state": "open_reject"})
        raise ToolCallError("tool_circuit_open", "일시적으로 툴 호출이 제한되었습니다. 잠시 후 다시 시도해 주세요.", status_code=503)

    url = f"{_commerce_base_url()}{path}"
    headers = {
        "x-user-id": str(user_id),
        "x-tenant-id": tenant_id,
        "x-trace-id": trace_id,
        "x-request-id": request_id,
        "content-type": "application/json",
        "accept": "application/json",
    }

    retries = _tool_lookup_retry_count()
    timeout_sec = _tool_lookup_timeout_sec()
    last_error: ToolCallError | None = None

    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_sec,
                )
            took_ms = int((time.perf_counter() - started) * 1000)
            metrics.inc("chat_tool_latency_ms", {"tool": tool_name}, value=max(1, took_ms))

            if response.status_code >= 400:
                payload_obj = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error = payload_obj.get("error") if isinstance(payload_obj, dict) else {}
                code = error.get("code") if isinstance(error, dict) else None
                message = error.get("message") if isinstance(error, dict) else None
                code = str(code or "tool_error")
                message = str(message or "툴 호출 중 오류가 발생했습니다.")
                if response.status_code == 403:
                    metrics.inc("chat_tool_authz_denied_total", {"intent": intent})
                    _audit_tool_authz_decision(
                        conversation_id=conversation_id,
                        action_type=tool_name,
                        user_id=user_id,
                        trace_id=trace_id,
                        request_id=request_id,
                        path=path,
                        decision="DENY",
                        result="BLOCKED",
                        reason_code="AUTH_FORBIDDEN",
                        status_code=403,
                    )
                if response.status_code >= 500 or response.status_code == 429:
                    _record_tool_failure(tool_name)
                raise ToolCallError(code=code, message=message, status_code=response.status_code)

            _record_tool_metrics(intent, tool_name, "ok")
            _record_tool_success(tool_name)
            _audit_tool_authz_decision(
                conversation_id=conversation_id,
                action_type=tool_name,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                path=path,
                decision="ALLOW",
                result="SUCCESS",
                reason_code="OK",
                status_code=response.status_code,
            )
            try:
                return response.json()
            except Exception:
                raise ToolCallError("schema_mismatch", "툴 응답 파싱에 실패했습니다.", status_code=response.status_code)
        except (httpx.TimeoutException, httpx.NetworkError):
            last_error = ToolCallError("tool_timeout", "툴 응답 시간이 초과되었습니다.", status_code=504)
            _record_tool_failure(tool_name)
            if attempt < retries:
                await asyncio.sleep(0.12 * (attempt + 1))
                continue
            _record_tool_metrics(intent, tool_name, "timeout")
            metrics.inc("chat_timeout_total", {"stage": "tool_lookup"})
            metrics.inc("chat_tool_fallback_total", {"reason_code": "tool_timeout"})
            raise last_error
        except ToolCallError as exc:
            last_error = exc
            if exc.status_code is not None and (exc.status_code >= 500 or exc.status_code == 429):
                _record_tool_failure(tool_name)
            if attempt < retries and (exc.status_code is None or exc.status_code >= 500):
                await asyncio.sleep(0.12 * (attempt + 1))
                continue
            _record_tool_metrics(intent, tool_name, "error")
            metrics.inc("chat_tool_fallback_total", {"reason_code": exc.code})
            raise exc

    raise last_error or ToolCallError("tool_error", "툴 호출에 실패했습니다.")


async def _resolve_order(order_ref: OrderRef, *, user_id: str, trace_id: str, request_id: str, intent: str) -> dict[str, Any]:
    if order_ref.order_id:
        data = await _call_commerce(
            "GET",
            f"/orders/{order_ref.order_id}",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="order_lookup",
            intent=intent,
        )
        order = data.get("order") if isinstance(data, dict) else None
        if not isinstance(order, dict):
            raise ToolCallError("order_not_found", "주문 정보를 찾을 수 없습니다.", status_code=404)
        return order

    if order_ref.order_no:
        data = await _call_commerce(
            "GET",
            "/orders?limit=100",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="order_lookup",
            intent=intent,
        )
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            raise ToolCallError("order_not_found", "주문 정보를 찾을 수 없습니다.", status_code=404)
        normalized_target = str(order_ref.order_no).strip().upper()
        for item in items:
            if not isinstance(item, dict):
                continue
            order_no = str(item.get("order_no") or "").strip().upper()
            if order_no == normalized_target:
                return item
        raise ToolCallError("order_not_found", "주문 정보를 찾을 수 없습니다.", status_code=404)

    raise ToolCallError("missing_order_reference", "주문번호를 확인할 수 없습니다.", status_code=400)


async def _handle_order_lookup(
    query: str,
    *,
    user_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    order_ref = _extract_order_ref(query)
    if order_ref.order_id is None and order_ref.order_no is None:
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "주문 조회를 위해 주문번호(예: ORD20260222XXXX) 또는 주문 ID를 입력해 주세요.",
        )

    try:
        order = await _resolve_order(order_ref, user_id=user_id, trace_id=trace_id, request_id=request_id, intent="ORDER_LOOKUP")
    except ToolCallError as exc:
        if exc.code == "order_not_found":
            return _build_response(trace_id, request_id, "not_found", "해당 주문을 찾을 수 없습니다. 주문번호를 다시 확인해 주세요.")
        if exc.status_code == 403:
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 조회할 수 있습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "주문 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    order_no = str(order.get("order_no") or "-")
    status = _order_status_ko(str(order.get("status") or ""))
    total_amount = _format_krw(order.get("total_amount"))
    shipping_fee = _format_krw(order.get("shipping_fee"))
    payment_method = str(order.get("payment_method") or "미지정")

    content = (
        f"주문 {order_no}의 현재 상태는 '{status}'입니다. "
        f"결제 금액은 {total_amount}, 배송비는 {shipping_fee}, 결제수단은 {payment_method}입니다."
    )
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="order_lookup",
        endpoint="GET /api/v1/orders/{orderId}",
        source_snippet=f"order_no={order_no}, status={status}",
    )


async def _handle_shipment_lookup(
    query: str,
    *,
    user_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    order_ref = _extract_order_ref(query)
    if order_ref.order_id is None and order_ref.order_no is None:
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "배송 조회를 위해 주문번호(예: ORD20260222XXXX) 또는 주문 ID를 입력해 주세요.",
        )

    try:
        order = await _resolve_order(order_ref, user_id=user_id, trace_id=trace_id, request_id=request_id, intent="SHIPMENT_LOOKUP")
    except ToolCallError as exc:
        if exc.code == "order_not_found":
            return _build_response(trace_id, request_id, "not_found", "해당 주문을 찾을 수 없습니다. 주문번호를 다시 확인해 주세요.")
        if exc.status_code == 403:
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 조회할 수 있습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "배송 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    order_id = int(order.get("order_id"))
    order_no = str(order.get("order_no") or "-")

    try:
        shipment_data = await _call_commerce(
            "GET",
            f"/shipments/by-order/{order_id}",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="shipment_lookup",
            intent="SHIPMENT_LOOKUP",
        )
    except ToolCallError:
        return _build_response(trace_id, request_id, "tool_fallback", "배송 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    items = shipment_data.get("items") if isinstance(shipment_data, dict) else []
    if not isinstance(items, list) or len(items) == 0:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            f"주문 {order_no}는 아직 배송 정보가 등록되지 않았습니다.",
            tool_name="shipment_lookup",
            endpoint="GET /api/v1/shipments/by-order/{orderId}",
            source_snippet=f"order_no={order_no}, shipment_count=0",
        )

    latest = items[0] if isinstance(items[0], dict) else {}
    shipment_status = _shipment_status_ko(str(latest.get("status") or ""))
    tracking_no = str(latest.get("tracking_no") or "미등록")
    carrier = str(latest.get("carrier") or "미지정")

    content = f"주문 {order_no}의 배송 상태는 '{shipment_status}'입니다. 운송사는 {carrier}, 운송장 번호는 {tracking_no}입니다."
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="shipment_lookup",
        endpoint="GET /api/v1/shipments/by-order/{orderId}",
        source_snippet=f"order_no={order_no}, shipment_status={shipment_status}",
    )


async def _handle_refund_lookup(
    query: str,
    *,
    user_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    order_ref = _extract_order_ref(query)
    if order_ref.order_id is None and order_ref.order_no is None:
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "환불 조회를 위해 주문번호(예: ORD20260222XXXX) 또는 주문 ID를 입력해 주세요.",
        )

    try:
        order = await _resolve_order(order_ref, user_id=user_id, trace_id=trace_id, request_id=request_id, intent="REFUND_LOOKUP")
    except ToolCallError as exc:
        if exc.code == "order_not_found":
            return _build_response(trace_id, request_id, "not_found", "해당 주문을 찾을 수 없습니다. 주문번호를 다시 확인해 주세요.")
        if exc.status_code == 403:
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 조회할 수 있습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "환불 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    order_id = int(order.get("order_id"))
    order_no = str(order.get("order_no") or "-")
    try:
        refund_data = await _call_commerce(
            "GET",
            f"/refunds/by-order/{order_id}",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="refund_lookup",
            intent="REFUND_LOOKUP",
        )
    except ToolCallError:
        return _build_response(trace_id, request_id, "tool_fallback", "환불 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    items = refund_data.get("items") if isinstance(refund_data, dict) else []
    if not isinstance(items, list) or len(items) == 0:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            f"주문 {order_no}는 현재 환불 접수 내역이 없습니다.",
            tool_name="refund_lookup",
            endpoint="GET /api/v1/refunds/by-order/{orderId}",
            source_snippet=f"order_no={order_no}, refund_count=0",
        )

    latest = items[0] if isinstance(items[0], dict) else {}
    refund_status = _refund_status_ko(str(latest.get("status") or ""))
    refund_amount = _format_krw(latest.get("amount"))

    content = f"주문 {order_no}의 최신 환불 상태는 '{refund_status}'이며, 환불 금액은 {refund_amount}입니다."
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="refund_lookup",
        endpoint="GET /api/v1/refunds/by-order/{orderId}",
        source_snippet=f"order_no={order_no}, refund_status={refund_status}",
    )


def _handle_refund_policy_guide(trace_id: str, request_id: str) -> dict[str, Any]:
    def _compose_refund_policy() -> tuple[str, str]:
        base_fee = _format_krw(_policy_base_shipping_fee())
        fast_fee = _format_krw(_policy_fast_shipping_fee())
        free_threshold = _format_krw(_policy_free_shipping_threshold())
        content = (
            "환불/반품 조건을 요약해드릴게요.\n"
            "- 결제 완료/배송 준비 단계에서 전체 취소 시 상품금액과 배송비를 환불합니다.\n"
            "- 배송 중/배송 완료 이후에는 환불 사유에 따라 환불 금액이 달라집니다.\n"
            "- 판매자 귀책(파손/오배송/하자/지연)은 배송비 포함 환불이 가능합니다.\n"
            f"- 단순 변심은 반품비가 차감되며, 기본 배송 {base_fee}, 빠른 배송 {fast_fee} 기준으로 계산됩니다.\n"
            "- 최종 환불액은 '상품금액 + 환불배송비 - 반품비'로 계산됩니다.\n"
            f"- 무료배송 기준은 {free_threshold}입니다.\n"
            "주문번호를 알려주시면 해당 주문 기준 예상 환불 금액을 바로 조회해드릴 수 있어요."
        )
        return content, "refund policy summary: order status, reason code, return fee, shipping refund"

    return _build_cached_policy_response(
        topic="refund",
        trace_id=trace_id,
        request_id=request_id,
        tool_name="refund_policy",
        endpoint="POLICY / commerce-refund-guide",
        content_builder=_compose_refund_policy,
    )


def _handle_shipping_policy_guide(trace_id: str, request_id: str) -> dict[str, Any]:
    def _compose_shipping_policy() -> tuple[str, str]:
        base_fee = _format_krw(_policy_base_shipping_fee())
        fast_fee = _format_krw(_policy_fast_shipping_fee())
        free_threshold = _format_krw(_policy_free_shipping_threshold())
        content = (
            "배송 정책을 요약해드릴게요.\n"
            f"- 기본 배송비는 {base_fee}, 빠른 배송비는 {fast_fee}입니다.\n"
            f"- 주문 금액이 {free_threshold} 이상이면 기본 배송비가 0원 처리됩니다.\n"
            "- 빠른 배송은 기본 배송보다 우선 출고되며, 결제 시 선택한 배송 방식으로 고정됩니다.\n"
            "- 배송 준비 이후에는 주소/옵션 변경이 제한될 수 있습니다.\n"
            "주문번호를 알려주시면 현재 배송 상태와 변경 가능 여부를 바로 확인해드릴게요."
        )
        return content, "shipping policy summary: base/fast fee, free-shipping threshold, change restrictions"

    return _build_cached_policy_response(
        topic="shipping",
        trace_id=trace_id,
        request_id=request_id,
        tool_name="shipping_policy",
        endpoint="POLICY / commerce-shipping-guide",
        content_builder=_compose_shipping_policy,
    )


def _handle_order_policy_guide(trace_id: str, request_id: str) -> dict[str, Any]:
    def _compose_order_policy() -> tuple[str, str]:
        content = (
            "주문/결제 진행 기준을 요약해드릴게요.\n"
            "- 주문 생성 → 결제 대기 → 결제 완료 → 배송 준비 → 배송 중 → 배송 완료 순서로 진행됩니다.\n"
            "- 결제 대기 상태에서는 결제 수단 변경 또는 취소가 가능합니다.\n"
            "- 결제 완료 이후 취소/환불은 배송 상태와 사유에 따라 가능 여부가 달라집니다.\n"
            "주문번호를 알려주시면 현재 단계와 지금 가능한 다음 액션을 정확히 안내해드릴게요."
        )
        return content, "order flow summary: created, paid, ready_to_ship, shipped, delivered"

    return _build_cached_policy_response(
        topic="order",
        trace_id=trace_id,
        request_id=request_id,
        tool_name="order_policy",
        endpoint="POLICY / commerce-order-guide",
        content_builder=_compose_order_policy,
    )


def _build_recommendation_reason(
    item: dict[str, Any],
    *,
    seed_book: dict[str, Any] | None = None,
    query_context: str = "",
) -> str:
    normalized_context = _normalize_text(query_context)
    score = item.get("score")
    if "더 쉬운" in normalized_context or "쉬운 버전" in normalized_context:
        title = str(item.get("title") or "").lower()
        easy_tokens = ["입문", "기초", "초급", "easy", "beginner", "첫걸음"]
        if any(token in title for token in easy_tokens):
            return "난이도 완화 요청에 맞는 입문/기초 성격의 후보입니다."
        return "난이도 완화 요청을 반영해 비교적 쉬운 후보를 우선 반영했습니다."

    if "다른 출판사" in normalized_context:
        candidate_publisher = str(item.get("publisher") or "").strip()
        seed_publisher = str((seed_book or {}).get("publisher") or "").strip()
        if candidate_publisher and seed_publisher and candidate_publisher != seed_publisher:
            return f"선택 도서와 다른 출판사({candidate_publisher}) 후보입니다."
        return "출판사 다양화 요청을 반영한 대체 후보입니다."

    if isinstance(score, (int, float)):
        numeric = float(score)
        if numeric >= 0.9:
            return "시드 도서와 주제/키워드 유사도가 높습니다."
        if numeric >= 0.75:
            return "시드 도서와 유사 주제를 다루는 후보입니다."
    return "시드 기준으로 장르/주제를 확장한 후보입니다."


def _format_recommendation_lines(
    items: list[dict[str, Any]],
    *,
    max_items: int = 5,
    seed_book: dict[str, Any] | None = None,
    query_context: str = "",
) -> list[str]:
    lines: list[str] = []
    for idx, item in enumerate(items[:max_items], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        author = str(item.get("author") or "").strip()
        doc_id = str(item.get("doc_id") or "").strip()
        score = item.get("score")
        score_text = ""
        if isinstance(score, (int, float)):
            score_text = f" · 유사도 {float(score):.2f}"
        meta_parts = [part for part in [author, doc_id] if part]
        meta = f" ({' / '.join(meta_parts)})" if meta_parts else ""
        reason = _build_recommendation_reason(item, seed_book=seed_book, query_context=query_context)
        lines.append(f"{idx}) {title}{meta}{score_text}\n   - 추천 이유: {reason}")
    return lines


async def _handle_book_recommendation(
    query: str,
    *,
    session_id: str,
    user_id: str | None,
    trace_id: str,
    request_id: str,
    seed_book: dict[str, Any] | None = None,
    followup_query: str | None = None,
) -> dict[str, Any]:
    raw_slots = extract_book_query_slots(query)
    context_seed_book = seed_book if isinstance(seed_book, dict) else {}
    context_seed_isbn = normalize_isbn(str(context_seed_book.get("isbn") or "").strip())
    context_seed_title = str(context_seed_book.get("title") or "").strip()
    effective_slots = BookQuerySlots(
        isbn=raw_slots.isbn or context_seed_isbn,
        title=raw_slots.title or (context_seed_title or None),
        series=raw_slots.series,
        volume=raw_slots.volume,
        format=raw_slots.format,
    )
    seed_query = _extract_recommendation_seed_query(query, book_slots=effective_slots)
    lookup_query = canonical_book_query(effective_slots, seed_query or query) or query
    followup_text = str(followup_query or "").strip()
    if context_seed_book and followup_text:
        seed_anchor = context_seed_title or str(effective_slots.title or effective_slots.isbn or lookup_query).strip()
        if seed_anchor:
            lookup_query = f"{seed_anchor} {followup_text}".strip()
    candidates = await retrieve_candidates(lookup_query, trace_id, request_id, top_k=10)

    if not candidates and seed_query and seed_query != query:
        candidates = await retrieve_candidates(query, trace_id, request_id, top_k=10)

    if not candidates:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "추천 후보를 찾지 못했습니다. 도서 제목/저자/ISBN 중 하나를 함께 입력해 주세요.",
            tool_name="book_recommend",
            endpoint="OS /books_doc_read/_search",
            source_snippet=f"seed_query={lookup_query}, slots={slots_to_dict(effective_slots)}, candidate_count=0",
        )

    normalized_seed = _normalize_title_for_compare(seed_query or str(effective_slots.title or context_seed_title))
    seed_isbn = effective_slots.isbn
    filtered: list[dict[str, Any]] = []
    seed_hit: dict[str, Any] | None = None
    for candidate in candidates:
        title = str(candidate.get("title") or "").strip()
        normalized_title = _normalize_title_for_compare(title)
        candidate_isbn = normalize_isbn(str(candidate.get("isbn") or "").strip())
        same_seed_by_isbn = bool(seed_isbn and candidate_isbn and seed_isbn == candidate_isbn)
        same_seed_by_title = bool(normalized_seed and normalized_title and normalized_title == normalized_seed)
        if same_seed_by_isbn or same_seed_by_title:
            if seed_hit is None:
                seed_hit = candidate
            continue
        filtered.append(candidate)

    recommended = filtered
    if not recommended and not normalized_seed:
        recommended = candidates
    lines = _format_recommendation_lines(
        recommended,
        max_items=5,
        seed_book=context_seed_book if context_seed_book else seed_hit,
        query_context=followup_text or query,
    )
    if not lines:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "현재 기준으로 동일 도서 외 유사 후보를 찾지 못했습니다. 제목/저자/카테고리를 함께 입력해 주세요.",
            tool_name="book_recommend",
            endpoint="OS /books_doc_read/_search",
            source_snippet=(
                f"seed_query={lookup_query}, slots={slots_to_dict(effective_slots)}, "
                f"candidate_count={len(candidates)}, filtered_count={len(filtered)}"
            ),
        )

    seed_title = ""
    if isinstance(seed_hit, dict):
        seed_title = str(seed_hit.get("title") or "").strip()
    elif isinstance(effective_slots.title, str) and effective_slots.title:
        seed_title = effective_slots.title
    elif isinstance(effective_slots.series, str) and effective_slots.series and isinstance(effective_slots.volume, int) and effective_slots.volume > 0:
        seed_title = f"{effective_slots.series} {effective_slots.volume}권"
    elif seed_query:
        seed_title = str(seed_query).strip()
    prefix = f"'{seed_title}' 기준 추천 도서입니다.\n" if seed_title else "요청하신 기준으로 추천 도서를 정리했습니다.\n"
    content = prefix + "\n".join(lines)
    selection_candidates = _build_selection_candidates(recommended, max_items=5)
    if selection_candidates:
        _save_selection_state(
            session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            candidates=selection_candidates,
            selected_index=None,
        )
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="book_recommend",
        endpoint="OS /books_doc_read/_search",
        source_snippet=f"seed_query={lookup_query}, slots={slots_to_dict(effective_slots)}, candidate_count={len(candidates)}",
    )


async def _handle_cart_recommendation(
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    try:
        cart_data = await _call_commerce(
            "GET",
            "/cart",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="cart_recommend",
            intent="CART_RECOMMEND",
        )
    except ToolCallError:
        return _build_response(trace_id, request_id, "tool_fallback", "장바구니 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    cart = cart_data.get("cart") if isinstance(cart_data, dict) else {}
    items = cart.get("items") if isinstance(cart, dict) else []
    if not isinstance(items, list) or not items:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "장바구니가 비어 있어 추천 기준이 없습니다. 도서를 먼저 장바구니에 담아주세요.",
            tool_name="cart_recommend",
            endpoint="GET /api/v1/cart",
            source_snippet="cart_item_count=0",
        )

    seed_titles = _pick_cart_seed_titles(items, limit=2)
    if not seed_titles:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "장바구니 도서 제목을 확인하지 못했습니다. 장바구니를 새로고침한 뒤 다시 시도해 주세요.",
            tool_name="cart_recommend",
            endpoint="GET /api/v1/cart",
            source_snippet=f"cart_item_count={len(items)}, seed_count=0",
        )

    merged: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()
    seed_normalized = {_normalize_title_for_compare(title) for title in seed_titles}
    for seed in seed_titles:
        candidates = await retrieve_candidates(seed, trace_id, request_id, top_k=6)
        for candidate in candidates:
            doc_id = str(candidate.get("doc_id") or "").strip()
            title = str(candidate.get("title") or "").strip()
            if not title:
                continue
            normalized_title = _normalize_title_for_compare(title)
            if normalized_title and normalized_title in seed_normalized:
                continue
            if doc_id and doc_id in seen_doc_ids:
                continue
            if doc_id:
                seen_doc_ids.add(doc_id)
            merged.append(candidate)
            if len(merged) >= 8:
                break
        if len(merged) >= 8:
            break

    if not merged:
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "장바구니 기준 추천 후보를 찾지 못했습니다. 장바구니 도서를 변경한 뒤 다시 시도해 주세요.",
            tool_name="cart_recommend",
            endpoint="GET /api/v1/cart",
            source_snippet=f"cart_item_count={len(items)}, seed_count={len(seed_titles)}, recommendation_count=0",
        )

    lines = _format_recommendation_lines(merged, max_items=5, query_context="cart")
    content = "장바구니 도서를 기준으로 추천 도서를 정리했습니다.\n" + "\n".join(lines)
    selection_candidates = _build_selection_candidates(merged, max_items=5)
    if selection_candidates:
        _save_selection_state(
            session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            candidates=selection_candidates,
            selected_index=None,
        )
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="cart_recommend",
        endpoint="GET /api/v1/cart",
        source_snippet=f"cart_item_count={len(items)}, seed_count={len(seed_titles)}, recommendation_count={len(merged)}",
    )


async def _start_sensitive_workflow(
    intent: str,
    query: str,
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    order_ref = _extract_order_ref(query)
    if order_ref.order_id is None and order_ref.order_no is None:
        action_label = "주문취소" if intent == "ORDER_CANCEL" else "환불접수"
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            f"{action_label}를 진행하려면 주문번호(예: ORD20260222XXXX) 또는 주문 ID를 먼저 입력해 주세요.",
        )

    try:
        order = await _resolve_order(order_ref, user_id=user_id, trace_id=trace_id, request_id=request_id, intent=intent)
    except ToolCallError as exc:
        if exc.code == "order_not_found":
            return _build_response(trace_id, request_id, "not_found", "해당 주문을 찾을 수 없습니다. 주문번호를 다시 확인해 주세요.")
        if exc.status_code == 403:
            metrics.inc("chat_sensitive_action_blocked_total", {"reason": "authz_denied"})
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 처리할 수 있습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "주문 정보를 확인하지 못해 작업을 시작할 수 없습니다.")

    order_id = int(order.get("order_id"))
    order_no = str(order.get("order_no") or f"#{order_id}")
    token = _build_confirmation_token(trace_id, request_id, session_id)
    workflow_type = intent
    risk = infer_risk_level(workflow_type)
    action_draft = build_action_draft(
        action_type=workflow_type,
        args={"order_id": order_id, "order_no": order_no},
        conversation_id=session_id,
        user_id=user_id,
        tenant_id=_tenant_id(),
        trace_id=trace_id,
        request_id=request_id,
        confirm_ttl_sec=_confirmation_token_ttl_sec(),
        dry_run=False,
        compensation_hint="open_support_ticket",
    )
    validation = validate_action_draft(action_draft)
    metrics.inc(
        "chat_action_validate_total",
        {
            "result": "ok" if validation.ok else "error",
            "action_type": workflow_type,
        },
    )
    if not validation.ok:
        metrics.inc("chat_bad_action_schema_total", {"action_type": workflow_type, "reason": validation.reason_code})
        return _build_response(
            trace_id,
            request_id,
            "invalid_state",
            "요청 형식을 검증하지 못해 작업을 시작할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            reason_code=validation.reason_code,
            next_action="OPEN_SUPPORT_TICKET",
        )
    workflow = {
        "workflow_id": f"wf:{session_id}:{request_id}",
        "workflow_type": workflow_type,
        "fsm_state": "INIT",
        "step": "init",
        "user_id": user_id,
        "order_id": order_id,
        "order_no": order_no,
        "risk": risk,
        "retry_count": 0,
        "max_retry": _workflow_retry_budget(),
        "action_draft": action_draft,
        "confirmation_token": token,
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + _confirmation_token_ttl_sec(),
    }
    _save_workflow(session_id, workflow, ttl_sec=_workflow_ttl_sec())
    _apply_workflow_transition(
        workflow,
        to_state="AWAITING_CONFIRMATION",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        reason_code="ROUTE:CONFIRM:AWAITING_CONFIRMATION",
        persist=True,
    )
    metrics.inc("chat_workflow_started_total", {"type": workflow_type})
    metrics.inc(
        "chat_sensitive_action_requested_total",
        {"action": "order_cancel" if workflow_type == "ORDER_CANCEL" else "refund_create", "risk": risk},
    )

    action_label = "주문취소" if workflow_type == "ORDER_CANCEL" else "환불접수"
    content = (
        f"{order_no} {action_label} 요청을 접수했습니다. "
        f"민감 작업이므로 확인 코드 [{token}]를 포함해 '확인 {token}'라고 입력해 주세요. "
        "확인 코드는 5분 후 만료됩니다."
    )
    return _build_response(
        trace_id,
        request_id,
        "pending_confirmation",
        content,
        tool_name="workflow_confirmation",
        endpoint="POST /chat/workflow/confirm",
        source_snippet=f"workflow_type={workflow_type}, order_no={order_no}",
    )


async def _handle_ticket_create(
    query: str,
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
    history_issue_context: str = "",
) -> dict[str, Any]:
    unresolved = _load_unresolved_context(session_id)
    unresolved_query = str(unresolved.get("query") or "").strip() if isinstance(unresolved, dict) else ""
    unresolved_reason = str(unresolved.get("reason_code") or "").strip() if isinstance(unresolved, dict) else ""
    generic_ticket_request = _is_generic_ticket_create_message(query)
    effective_query = query
    if generic_ticket_request and unresolved_query:
        effective_query = unresolved_query
        metrics.inc("chat_ticket_create_with_context_total", {"source": "unresolved_context"})
    elif generic_ticket_request and history_issue_context:
        effective_query = history_issue_context
        metrics.inc("chat_ticket_create_with_context_total", {"source": "history"})
    elif generic_ticket_request:
        metrics.inc("chat_ticket_needs_input_total", {"reason": "missing_issue_context"})
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "문의 내용을 조금 더 자세히 입력해 주세요. 예: '주문 12 환불이 진행되지 않아요'.",
            reason_code="MISSING_REQUIRED_INFO",
            recoverable=True,
            next_action="PROVIDE_REQUIRED_INFO",
        )

    if len(effective_query.strip()) < 8:
        metrics.inc("chat_ticket_needs_input_total", {"reason": "query_too_short"})
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "문의 내용을 8자 이상으로 구체적으로 입력해 주세요.",
            reason_code="MISSING_REQUIRED_INFO",
            recoverable=True,
            next_action="PROVIDE_REQUIRED_INFO",
        )

    dedup_fingerprint = _ticket_create_fingerprint(user_id, effective_query)
    dedup_cached, dedup_scope = _load_ticket_create_dedup(session_id, user_id, dedup_fingerprint)
    metrics.inc("chat_ticket_create_dedup_lookup_total", {"result": dedup_scope or "miss"})
    if isinstance(dedup_cached, dict):
        cached_ticket_no = str(dedup_cached.get("ticket_no") or "")
        cached_status = str(dedup_cached.get("status") or "RECEIVED")
        cached_status_ko = _ticket_status_ko(cached_status)
        cached_eta_minutes = int(dedup_cached.get("expected_response_minutes") or 0)
        if cached_ticket_no:
            metrics.inc("chat_ticket_create_dedup_hit_total", {"result": "reused"})
            metrics.inc("chat_ticket_create_dedup_scope_total", {"scope": dedup_scope or "unknown"})
            metrics.inc("chat_ticket_create_rate_limited_total", {"result": "dedup_bypass"})
            _save_last_ticket_no(session_id, user_id, cached_ticket_no)
            _save_ticket_create_last(session_id, user_id)
            _clear_unresolved_context(session_id)
            _reset_fallback_counter(session_id)
            metrics.inc("chat_ticket_context_reset_total", {"reason": "ticket_reused"})
            return _build_response(
                trace_id,
                request_id,
                "ok",
                (
                    f"방금 동일한 문의를 접수한 이력이 있어 기존 접수번호 {cached_ticket_no}를 재사용합니다. "
                    f"현재 상태는 '{cached_status_ko}'이며 예상 첫 응답은 약 {cached_eta_minutes}분입니다."
                ),
                tool_name="ticket_create",
                endpoint="POST /api/v1/support/tickets",
                source_snippet=f"ticket_no={cached_ticket_no}, dedup=true, status={cached_status}",
            )

    cooldown_sec = _ticket_create_cooldown_sec()
    if cooldown_sec > 0:
        last_created_at = _load_ticket_create_last(session_id, user_id)
        now_ts = int(time.time())
        if isinstance(last_created_at, int):
            remaining_sec = (last_created_at + cooldown_sec) - now_ts
            if remaining_sec > 0:
                metrics.inc("chat_ticket_create_rate_limited_total", {"result": "blocked"})
                recent_ticket_no = _load_last_ticket_no(session_id, user_id)
                metrics.inc(
                    "chat_ticket_create_rate_limited_context_total",
                    {"has_recent_ticket": "true" if recent_ticket_no else "false"},
                )
                if recent_ticket_no:
                    message = (
                        f"문의가 방금 접수되었습니다. 기존 접수번호는 {recent_ticket_no}입니다. "
                        f"{remaining_sec}초 후 다시 시도해 주세요."
                    )
                else:
                    message = f"문의가 방금 접수되었습니다. {remaining_sec}초 후 다시 시도해 주세요."
                return _build_response(
                    trace_id,
                    request_id,
                    "needs_input",
                    message,
                    reason_code="RATE_LIMITED",
                    recoverable=True,
                    next_action="RETRY",
                    retry_after_ms=remaining_sec * 1000,
                    tool_name="ticket_create_cooldown",
                    endpoint="POST /api/v1/support/tickets",
                    source_snippet=f"cooldown_sec={cooldown_sec}, remaining_sec={remaining_sec}, recent_ticket_no={recent_ticket_no or '-'}",
                )
        metrics.inc("chat_ticket_create_rate_limited_total", {"result": "pass"})

    category = _infer_ticket_category(effective_query)
    severity = _infer_ticket_severity(effective_query)
    order_ref = _extract_order_ref(effective_query)
    order_id: int | None = None
    if order_ref.order_id is not None or order_ref.order_no is not None:
        try:
            order = await _resolve_order(order_ref, user_id=user_id, trace_id=trace_id, request_id=request_id, intent="TICKET_CREATE")
            order_id = int(order.get("order_id"))
        except ToolCallError as exc:
            if exc.status_code == 403:
                metrics.inc("chat_ticket_authz_denied_total")
                return _build_response(trace_id, request_id, "forbidden", "본인 주문 기반 문의만 접수할 수 있습니다.")
            if exc.code == "order_not_found":
                return _build_response(trace_id, request_id, "not_found", "문의에 연결할 주문 정보를 찾지 못했습니다. 주문번호를 다시 확인해 주세요.")

    payload = {
        "orderId": order_id,
        "category": category,
        "severity": severity,
        "summary": effective_query[:255],
        "details": {
            "query": query,
            "effectiveQuery": effective_query,
            "unresolvedReasonCode": unresolved_reason or None,
            "unresolvedTraceId": (unresolved or {}).get("trace_id") if isinstance(unresolved, dict) else None,
            "unresolvedRequestId": (unresolved or {}).get("request_id") if isinstance(unresolved, dict) else None,
        },
        "errorCode": "CHAT_UNRESOLVED",
        "chatSessionId": session_id,
        "chatRequestId": request_id,
    }

    try:
        created = await _call_commerce(
            "POST",
            "/support/tickets",
            payload=payload,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="ticket_create",
            intent="TICKET_CREATE",
        )
    except ToolCallError as exc:
        if exc.status_code == 403:
            metrics.inc("chat_ticket_authz_denied_total")
            return _build_response(trace_id, request_id, "forbidden", "본인 티켓만 접수할 수 있습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "문의 접수 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    ticket = created.get("ticket") if isinstance(created, dict) else {}
    ticket_no = str(ticket.get("ticket_no") or "")
    status = str(ticket.get("status") or "RECEIVED")
    status_ko = _ticket_status_ko(status)
    eta_minutes = int(created.get("expected_response_minutes") or 0)
    _save_last_ticket_no(session_id, user_id, ticket_no)
    _save_ticket_create_last(session_id, user_id)
    _save_ticket_create_dedup(
        session_id,
        user_id,
        dedup_fingerprint,
        {
            "ticket_no": ticket_no,
            "status": status,
            "expected_response_minutes": eta_minutes,
        },
    )
    _clear_unresolved_context(session_id)
    _reset_fallback_counter(session_id)
    metrics.inc("chat_ticket_created_total", {"category": category})
    metrics.inc("chat_ticket_context_reset_total", {"reason": "ticket_created"})

    content = (
        f"문의가 접수되었습니다. 접수번호는 {ticket_no}, 현재 상태는 '{status_ko}'입니다. "
        f"예상 첫 응답 시간은 약 {eta_minutes}분입니다."
    )
    if unresolved_reason:
        content += f" 직전 실패 사유({unresolved_reason})도 함께 전달했습니다."
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="ticket_create",
        endpoint="POST /api/v1/support/tickets",
        source_snippet=f"ticket_no={ticket_no}, status={status}",
    )


async def _handle_ticket_status(
    query: str,
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    async def _load_latest_ticket_no_from_list() -> tuple[str | None, str]:
        try:
            listed = await _call_commerce(
                "GET",
                "/support/tickets?limit=1",
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                tool_name="ticket_status_lookup",
                intent="TICKET_STATUS",
            )
        except ToolCallError:
            metrics.inc("chat_ticket_status_recent_lookup_total", {"result": "error"})
            return None, "error"
        items = listed.get("items") if isinstance(listed, dict) else []
        if isinstance(items, list) and items:
            latest = items[0] if isinstance(items[0], dict) else {}
            candidate_ticket_no = str(latest.get("ticket_no") or "").strip().upper()
            if candidate_ticket_no:
                metrics.inc("chat_ticket_status_recent_lookup_total", {"result": "found"})
                return candidate_ticket_no, "found"
        metrics.inc("chat_ticket_status_recent_lookup_total", {"result": "empty"})
        return None, "empty"

    source = "query"
    ticket_no = _extract_ticket_no(query)
    if not ticket_no:
        source = "cache"
        ticket_no = _load_last_ticket_no(session_id, user_id)
    if not ticket_no:
        source = "list"
        ticket_no, list_result = await _load_latest_ticket_no_from_list()
        if not ticket_no:
            result_label = "recent_lookup_error" if list_result == "error" else "needs_input"
            message = (
                "최근 문의 내역을 조회하지 못했습니다. 접수번호(예: STK202602230001)를 입력해 주세요."
                if list_result == "error"
                else "최근 접수된 문의가 없습니다. 접수번호(예: STK202602230001)를 입력해 주세요."
            )
            metrics.inc("chat_ticket_status_lookup_total", {"result": result_label})
            metrics.inc("chat_ticket_status_lookup_ticket_source_total", {"source": "missing"})
            return _build_response(
                trace_id,
                request_id,
                "needs_input",
                message,
            )
        _save_last_ticket_no(session_id, user_id, ticket_no)
    if not ticket_no:
        metrics.inc("chat_ticket_status_lookup_total", {"result": "needs_input"})
        metrics.inc("chat_ticket_status_lookup_ticket_source_total", {"source": "missing"})
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "최근 접수된 문의가 없습니다. 접수번호(예: STK202602230001)를 입력해 주세요.",
        )
    metrics.inc("chat_ticket_status_lookup_ticket_source_total", {"source": source})

    try:
        looked_up = await _call_commerce(
            "GET",
            f"/support/tickets/by-number/{ticket_no}",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="ticket_status_lookup",
            intent="TICKET_STATUS",
        )
    except ToolCallError as exc:
        if source == "cache" and exc.code == "not_found":
            refreshed_ticket_no, _ = await _load_latest_ticket_no_from_list()
            if refreshed_ticket_no and refreshed_ticket_no != ticket_no:
                _save_last_ticket_no(session_id, user_id, refreshed_ticket_no)
                metrics.inc("chat_ticket_status_lookup_ticket_source_total", {"source": "list"})
                try:
                    looked_up = await _call_commerce(
                        "GET",
                        f"/support/tickets/by-number/{refreshed_ticket_no}",
                        user_id=user_id,
                        trace_id=trace_id,
                        request_id=request_id,
                        tool_name="ticket_status_lookup",
                        intent="TICKET_STATUS",
                    )
                    ticket_no = refreshed_ticket_no
                    metrics.inc("chat_ticket_status_lookup_cache_recovery_total", {"result": "recovered"})
                    exc = None
                except ToolCallError as retry_exc:
                    metrics.inc("chat_ticket_status_lookup_cache_recovery_total", {"result": "retry_failed"})
                    exc = retry_exc
            else:
                metrics.inc("chat_ticket_status_lookup_cache_recovery_total", {"result": "miss"})
        if exc is None:
            pass
        elif exc.status_code == 403:
            metrics.inc("chat_ticket_authz_denied_total")
            metrics.inc("chat_ticket_status_lookup_total", {"result": "forbidden"})
            return _build_response(trace_id, request_id, "forbidden", "본인 티켓만 조회할 수 있습니다.")
        elif exc.code == "not_found":
            metrics.inc("chat_ticket_status_lookup_total", {"result": "not_found"})
            return _build_response(trace_id, request_id, "not_found", "해당 접수번호의 문의를 찾을 수 없습니다.")
        elif exc is not None:
            metrics.inc("chat_ticket_status_lookup_total", {"result": "error"})
            return _build_response(trace_id, request_id, "tool_fallback", "티켓 상태를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    ticket = looked_up.get("ticket") if isinstance(looked_up, dict) else {}
    status = str(ticket.get("status") or "RECEIVED")
    status_ko = _ticket_status_ko(status)
    category_ko = _ticket_category_ko(str(ticket.get("category") or ""))
    severity_ko = _ticket_severity_ko(str(ticket.get("severity") or ""))
    eta_minutes = int(looked_up.get("expected_response_minutes") or 0) if isinstance(looked_up, dict) else 0
    followup = _ticket_followup_message(status)
    ticket_id = int(ticket.get("ticket_id") or 0) if isinstance(ticket, dict) else 0
    event_message = ""
    if ticket_id > 0:
        try:
            event_data = await _call_commerce(
                "GET",
                f"/support/tickets/{ticket_id}/events",
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                tool_name="ticket_status_events",
                intent="TICKET_STATUS",
            )
        except Exception:
            metrics.inc("chat_ticket_status_event_lookup_total", {"result": "error"})
        else:
            events = event_data.get("items") if isinstance(event_data, dict) else []
            if isinstance(events, list) and events:
                latest_event = events[-1] if isinstance(events[-1], dict) else {}
                event_type_ko = _ticket_event_type_ko(str(latest_event.get("event_type") or ""))
                event_note = str(latest_event.get("note") or "").strip()
                event_at = _format_event_timestamp(latest_event.get("created_at"))
                event_message = f"최근 처리 이력은 '{event_type_ko}'"
                if event_at:
                    event_message += f" ({event_at})"
                if event_note:
                    event_message += f" - {event_note}"
                event_message += "입니다."
                metrics.inc("chat_ticket_status_event_lookup_total", {"result": "ok"})
            else:
                metrics.inc("chat_ticket_status_event_lookup_total", {"result": "empty"})
    metrics.inc("chat_ticket_status_lookup_total", {"result": "ok"})
    metrics.inc("chat_ticket_followup_prompt_total", {"status": status})

    eta_message = (
        f"예상 첫 응답은 약 {eta_minutes}분입니다."
        if eta_minutes > 0
        else "예상 응답 시간은 담당자 배정 후 안내됩니다."
    )
    _save_last_ticket_no(session_id, user_id, ticket_no)
    content = (
        f"접수번호 {ticket_no}의 현재 상태는 '{status_ko}'입니다. "
        f"문의 유형은 '{category_ko}', 중요도는 '{severity_ko}'로 접수되어 있습니다. "
        f"{eta_message} {followup}"
    )
    if event_message:
        content += f" {event_message}"
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="ticket_status_lookup",
        endpoint="GET /api/v1/support/tickets/by-number/{ticketNo}",
        source_snippet=f"ticket_no={ticket_no}, status={status}",
    )


async def _handle_ticket_list(
    query: str,
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    limit = _extract_ticket_list_limit(query)
    try:
        listed = await _call_commerce(
            "GET",
            f"/support/tickets?limit={limit}",
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name="ticket_list",
            intent="TICKET_LIST",
        )
    except ToolCallError as exc:
        if exc.status_code == 403:
            metrics.inc("chat_ticket_authz_denied_total")
            metrics.inc("chat_ticket_list_total", {"result": "forbidden"})
            return _build_response(trace_id, request_id, "forbidden", "본인 티켓만 조회할 수 있습니다.")
        metrics.inc("chat_ticket_list_total", {"result": "error"})
        return _build_response(trace_id, request_id, "tool_fallback", "문의 내역을 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    items = listed.get("items") if isinstance(listed, dict) else []
    if not isinstance(items, list) or not items:
        metrics.inc("chat_ticket_list_total", {"result": "empty"})
        return _build_response(
            trace_id,
            request_id,
            "ok",
            "현재 접수된 문의 내역이 없습니다. 문제가 있으면 '문의 접수해줘 ...' 형태로 알려주세요.",
            tool_name="ticket_list",
            endpoint="GET /api/v1/support/tickets",
            source_snippet=f"ticket_count=0, limit={limit}",
        )

    lines: list[str] = []
    latest_ticket_no = ""
    for idx, item in enumerate(items[:limit], start=1):
        if not isinstance(item, dict):
            continue
        ticket_no = str(item.get("ticket_no") or "-").strip().upper()
        status = _ticket_status_ko(str(item.get("status") or ""))
        category = _ticket_category_ko(str(item.get("category") or ""))
        severity = _ticket_severity_ko(str(item.get("severity") or ""))
        if idx == 1 and ticket_no and ticket_no != "-":
            latest_ticket_no = ticket_no
        lines.append(f"{idx}) {ticket_no} · {status} · {category} · {severity}")

    if latest_ticket_no:
        _save_last_ticket_no(session_id, user_id, latest_ticket_no)

    metrics.inc("chat_ticket_list_total", {"result": "ok"})
    content = "최근 문의 내역입니다.\n" + "\n".join(lines)
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="ticket_list",
        endpoint="GET /api/v1/support/tickets",
        source_snippet=f"ticket_count={len(items)}, limit={limit}",
    )


async def _execute_sensitive_workflow(
    workflow: dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    workflow_type = str(workflow.get("workflow_type") or "")
    try:
        order_id = int(workflow.get("order_id"))
    except Exception:
        order_id = 0
    order_no = str(workflow.get("order_no") or f"#{order_id}")
    current_state = _workflow_fsm_state(workflow)
    action_draft = workflow.get("action_draft")
    validation = validate_action_draft(action_draft)
    metrics.inc(
        "chat_action_validate_total",
        {
            "result": "ok" if validation.ok else "error",
            "action_type": workflow_type or "unknown",
        },
    )
    if not validation.ok:
        metrics.inc("chat_bad_action_schema_total", {"action_type": workflow_type or "unknown", "reason": validation.reason_code})
        _apply_workflow_transition(
            workflow,
            to_state="FAILED_FINAL",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code=validation.reason_code,
            persist=False,
        )
        _clear_workflow(session_id)
        return _build_response(
            trace_id,
            request_id,
            "invalid_state",
            "요청 실행 규격을 검증하지 못했습니다. 다시 시도해 주세요.",
            reason_code=validation.reason_code,
            next_action="OPEN_SUPPORT_TICKET",
        )

    action_draft_obj = action_draft if isinstance(action_draft, dict) else {}
    idempotency_key = str(action_draft_obj.get("idempotency_key") or "").strip()
    if not idempotency_key:
        metrics.inc("chat_action_idempotency_reject_total", {"action_type": workflow_type or "unknown"})
        _apply_workflow_transition(
            workflow,
            to_state="FAILED_FINAL",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code="IDEMPOTENCY_REQUIRED",
            persist=False,
        )
        _clear_workflow(session_id)
        return _build_response(
            trace_id,
            request_id,
            "invalid_state",
            "중복 실행 방지 키가 없어 요청을 실행할 수 없습니다.",
            reason_code="IDEMPOTENCY_REQUIRED",
            next_action="OPEN_SUPPORT_TICKET",
        )

    if current_state != "CONFIRMED":
        metrics.inc("chat_execute_block_total", {"reason": "not_confirmed"})
        return _build_response(
            trace_id,
            request_id,
            "pending_confirmation",
            "확인 절차가 완료되지 않아 실행할 수 없습니다. 확인 코드를 입력해 주세요.",
            reason_code="DENY_EXECUTE:NOT_CONFIRMED",
            next_action="CONFIRM_ACTION",
        )

    receipt_key = _workflow_action_receipt_cache_key(idempotency_key)
    cached_receipt = _CACHE.get_json(receipt_key)
    if isinstance(cached_receipt, dict) and isinstance(cached_receipt.get("response"), dict):
        metrics.inc("chat_action_idempotency_reject_total", {"action_type": workflow_type})
        append_action_audit(
            conversation_id=session_id,
            action_type=workflow_type,
            action_state="EXECUTED",
            decision="ALLOW",
            result="SUCCESS",
            actor_user_id=user_id,
            actor_admin_id=None,
            target_ref=order_no,
            auth_context={"tenant_id": _tenant_id(), "user_id": user_id},
            trace_id=trace_id,
            request_id=request_id,
            reason_code="IDEMPOTENT_REPLAY",
            idempotency_key=idempotency_key,
            metadata={"workflow_state": current_state},
        )
        _clear_workflow(session_id)
        response = cached_receipt.get("response")
        if isinstance(response, dict):
            return response

    if not _apply_workflow_transition(
        workflow,
        to_state="EXECUTING",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        reason_code="FSM:EXECUTING",
        persist=True,
    ):
        return _build_response(
            trace_id,
            request_id,
            "invalid_state",
            "작업 상태 전이가 유효하지 않아 요청을 중단했습니다.",
            reason_code="INVALID_WORKFLOW_TRANSITION",
        )

    try:
        if workflow_type == "ORDER_CANCEL":
            args = action_draft_obj.get("args") if isinstance(action_draft_obj.get("args"), dict) else {}
            cancel_result = await _call_commerce(
                "POST",
                f"/orders/{order_id}/cancel",
                payload={"reason": "CHAT_CONFIRMATION"},
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                tool_name="order_cancel",
                intent="ORDER_CANCEL",
            )
            order = cancel_result.get("order") if isinstance(cancel_result, dict) else {}
            status = _order_status_ko(str(order.get("status") or ""))
            response = _build_response(
                trace_id,
                request_id,
                "ok",
                f"주문 {order_no} 취소가 완료되었습니다. 현재 상태는 '{status}'입니다.",
                tool_name="order_cancel",
                endpoint="POST /api/v1/orders/{orderId}/cancel",
                source_snippet=f"order_no={order_no}, status={status}",
            )
            _CACHE.set_json(receipt_key, {"response": response}, ttl=_workflow_action_receipt_ttl_sec())
            _apply_workflow_transition(
                workflow,
                to_state="EXECUTED",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                reason_code="FSM:EXECUTED",
                persist=False,
                metadata={"action_args": args},
            )
            _clear_workflow(session_id)
            metrics.inc("chat_sensitive_action_confirmed_total", {"action": "order_cancel"})
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "success"})
            return response

        if workflow_type == "REFUND_CREATE":
            args = action_draft_obj.get("args") if isinstance(action_draft_obj.get("args"), dict) else {}
            refund_result = await _call_commerce(
                "POST",
                "/refunds",
                payload={
                    "orderId": order_id,
                    "reasonCode": "OTHER",
                    "reasonText": "CHAT_REQUEST",
                    "idempotencyKey": idempotency_key,
                },
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                tool_name="refund_create",
                intent="REFUND_CREATE",
            )
            refund = refund_result.get("refund") if isinstance(refund_result, dict) else {}
            refund_id = str(refund.get("refund_id") or "-")
            refund_status = _refund_status_ko(str(refund.get("status") or ""))
            refund_amount = _format_krw(refund.get("amount"))
            response = _build_response(
                trace_id,
                request_id,
                "ok",
                f"주문 {order_no} 환불 접수가 완료되었습니다. 접수번호는 {refund_id}, 상태는 '{refund_status}', 예상 환불 금액은 {refund_amount}입니다.",
                tool_name="refund_create",
                endpoint="POST /api/v1/refunds",
                source_snippet=f"order_no={order_no}, refund_id={refund_id}, status={refund_status}",
            )
            _CACHE.set_json(receipt_key, {"response": response}, ttl=_workflow_action_receipt_ttl_sec())
            _apply_workflow_transition(
                workflow,
                to_state="EXECUTED",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                reason_code="FSM:EXECUTED",
                persist=False,
                metadata={"action_args": args},
            )
            _clear_workflow(session_id)
            metrics.inc("chat_sensitive_action_confirmed_total", {"action": "refund_create"})
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "success"})
            return response
    except ToolCallError as exc:
        metrics.inc("chat_workflow_step_error_total", {"type": workflow_type, "step": "execute", "error_code": exc.code})
        retry_count = int(workflow.get("retry_count") or 0)
        max_retry = int(workflow.get("max_retry") or _workflow_retry_budget())
        is_retryable = bool(
            exc.status_code is None
            or exc.status_code >= 500
            or exc.status_code == 429
            or exc.code in {"tool_timeout", "tool_circuit_open"}
        )
        if exc.status_code == 403:
            metrics.inc("chat_sensitive_action_blocked_total", {"reason": "authz_denied"})
            _apply_workflow_transition(
                workflow,
                to_state="FAILED_FINAL",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                reason_code="AUTH_FORBIDDEN",
                persist=False,
            )
            _clear_workflow(session_id)
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "blocked"})
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 처리할 수 있습니다.")
        if exc.code == "invalid_state":
            _apply_workflow_transition(
                workflow,
                to_state="FAILED_FINAL",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                reason_code="INVALID_WORKFLOW_STATE",
                persist=False,
            )
            _clear_workflow(session_id)
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "invalid_state"})
            return _build_response(trace_id, request_id, "invalid_state", "현재 주문 상태에서는 요청한 작업을 진행할 수 없습니다.")
        if is_retryable and retry_count < max_retry:
            workflow["retry_count"] = retry_count + 1
            _apply_workflow_transition(
                workflow,
                to_state="FAILED_RETRYABLE",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                request_id=request_id,
                reason_code="TOOL_RETRYABLE_FAILURE",
                persist=True,
                metadata={"retry_count": workflow["retry_count"], "max_retry": max_retry},
            )
            return _build_response(
                trace_id,
                request_id,
                "tool_fallback",
                "작업 실행 중 일시 오류가 발생했습니다. 동일한 확인 코드를 다시 입력하면 재시도합니다.",
                reason_code="TOOL_RETRYABLE_FAILURE",
                next_action="RETRY",
            )
        _apply_workflow_transition(
            workflow,
            to_state="FAILED_FINAL",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code="TOOL_FINAL_FAILURE",
            persist=False,
            metadata={"retry_count": retry_count, "max_retry": max_retry},
        )
        _clear_workflow(session_id)
        metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "failed_final"})
        return _build_response(trace_id, request_id, "tool_fallback", "작업 실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    metrics.inc("chat_workflow_step_error_total", {"type": workflow_type, "step": "execute", "error_code": "unsupported"})
    _apply_workflow_transition(
        workflow,
        to_state="FAILED_FINAL",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        reason_code="UNSUPPORTED_WORKFLOW",
        persist=False,
    )
    _clear_workflow(session_id)
    metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "unsupported"})
    return _build_response(trace_id, request_id, "unsupported", "지원하지 않는 워크플로우입니다.")


async def _handle_pending_workflow(
    query: str,
    workflow: dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    token = str(workflow.get("confirmation_token") or "")
    expected_user_id = str(workflow.get("user_id") or "")
    workflow_type = str(workflow.get("workflow_type") or "")
    state = _workflow_fsm_state(workflow)

    if expected_user_id and expected_user_id != str(user_id):
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "user_mismatch"})
        _apply_workflow_transition(
            workflow,
            to_state="ABORTED",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code="AUTH_FORBIDDEN",
            persist=False,
        )
        _clear_workflow(session_id)
        return _build_response(trace_id, request_id, "forbidden", "다른 사용자 세션의 작업은 확인할 수 없습니다.")

    if state == "EXECUTING":
        return _build_response(
            trace_id,
            request_id,
            "pending_confirmation",
            "현재 요청을 처리 중입니다. 잠시 후 상태를 다시 확인해 주세요.",
            reason_code="FSM_EXECUTING",
            next_action="STATUS_CHECK",
        )

    if state in _WORKFLOW_TERMINAL_STATES:
        _clear_workflow(session_id)
        if state == "EXECUTED":
            action_draft = workflow.get("action_draft") if isinstance(workflow.get("action_draft"), dict) else {}
            idempotency_key = str(action_draft.get("idempotency_key") or "").strip()
            if idempotency_key:
                cached = _CACHE.get_json(_workflow_action_receipt_cache_key(idempotency_key))
                if isinstance(cached, dict) and isinstance(cached.get("response"), dict):
                    return cached.get("response")
            return _build_response(trace_id, request_id, "ok", "요청이 이미 처리되었습니다.", reason_code="IDEMPOTENT_REPLAY")
        if state == "ABORTED":
            return _build_response(trace_id, request_id, "aborted", "요청이 이미 취소되었습니다.")
        if state == "EXPIRED":
            return _build_response(trace_id, request_id, "expired", "확인 기한이 만료되었습니다. 요청을 다시 시작해 주세요.")
        if state == "FAILED_FINAL":
            return _build_response(trace_id, request_id, "tool_fallback", "이전 요청이 실패했습니다. 새로 요청해 주세요.")

    expires_at = int(workflow.get("expires_at") or 0)
    if state in _WORKFLOW_PENDING_STATES and expires_at > 0 and int(time.time()) > expires_at:
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "confirmation_expired"})
        _apply_workflow_transition(
            workflow,
            to_state="EXPIRED",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code="CONFIRMATION_EXPIRED",
            persist=False,
        )
        _clear_workflow(session_id)
        metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "expired"})
        return _build_response(trace_id, request_id, "expired", "확인 코드가 만료되어 요청이 취소되었습니다. 다시 요청해 주세요.")

    if _is_abort_message(query) and "확인" not in _normalize_text(query):
        _apply_workflow_transition(
            workflow,
            to_state="ABORTED",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            reason_code="USER_ABORTED",
            persist=False,
        )
        _clear_workflow(session_id)
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "user_aborted"})
        metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "aborted"})
        return _build_response(trace_id, request_id, "aborted", "요청하신 작업을 취소했습니다.")

    if not _is_confirmation_message(query):
        if state == "FAILED_RETRYABLE":
            return _build_response(
                trace_id,
                request_id,
                "pending_confirmation",
                f"이전 실행이 실패했습니다. 동일 코드 [{token}]를 포함해 '확인 {token}'라고 입력하면 재시도합니다.",
                reason_code="RETRY_CONFIRMATION_REQUIRED",
                next_action="RETRY",
            )
        return _build_response(
            trace_id,
            request_id,
            "pending_confirmation",
            f"계속 진행하려면 확인 코드 [{token}]를 포함해 '확인 {token}'라고 입력해 주세요.",
        )

    provided = _extract_confirmation_token(query)
    if not provided or provided != token:
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "invalid_confirmation_token"})
        return _build_response(
            trace_id,
            request_id,
            "pending_confirmation",
            f"확인 코드가 일치하지 않습니다. 코드 [{token}]를 정확히 입력해 주세요.",
        )

    if not _apply_workflow_transition(
        workflow,
        to_state="CONFIRMED",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        reason_code="CONFIRMATION_ACCEPTED",
        persist=True,
    ):
        return _build_response(
            trace_id,
            request_id,
            "invalid_state",
            "확인 상태를 갱신하지 못해 요청을 중단했습니다.",
            reason_code="INVALID_WORKFLOW_TRANSITION",
        )

    return await _execute_sensitive_workflow(
        workflow,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        request_id=request_id,
    )


async def run_tool_chat(request: dict[str, Any], trace_id: str, request_id: str) -> dict[str, Any] | None:
    if not _tool_enabled():
        return None

    query = _extract_query_text(request)
    user_id = _extract_user_id(request)
    session_id = _resolve_session_id(request, user_id)
    history_issue_context = _extract_recent_issue_from_history(request)
    pending_workflow = _load_workflow(session_id) if user_id else None
    pending_state = _workflow_fsm_state(pending_workflow)
    selection_state = _selection_state_from_db(session_id)
    has_selection_state = isinstance(selection_state, dict)
    is_reference_query = _looks_like_reference_query(query, has_selection_state=has_selection_state)
    is_selection_followup_query = _looks_like_selection_followup_query(query)
    intent = _detect_intent(query)
    order_ref = _extract_order_ref(query)
    has_order_ref = order_ref.order_id is not None or order_ref.order_no is not None
    slots: dict[str, Any] = {"order_ref": {"order_id": order_ref.order_id, "order_no": order_ref.order_no} if has_order_ref else None}
    book_slots = extract_book_query_slots(query)
    book_slot_payload = slots_to_dict(book_slots)
    if any(value is not None and value != "" for value in book_slot_payload.values()):
        slots["book_query"] = book_slot_payload
    ticket_no = _extract_ticket_no(query)
    if ticket_no:
        slots["ticket_no"] = ticket_no
    standalone_query = query
    if intent.name == "BOOK_RECOMMEND":
        recommendation_seed = _extract_recommendation_seed_query(query, book_slots=book_slots)
        standalone_query = canonical_book_query(book_slots, recommendation_seed or query) or query
    understanding = build_understanding(
        query=query,
        intent=intent.name,
        slots=slots,
        standalone_query=standalone_query,
        risk_level=infer_risk_level(intent.name),
    )
    decision = decide_route(
        understanding,
        has_user=bool(user_id),
        has_pending_action=bool(isinstance(pending_workflow, dict) and pending_state in _WORKFLOW_PENDING_STATES),
        pending_state=pending_state,
        is_reference_query=is_reference_query,
        has_selection_state=has_selection_state,
    )
    _record_policy_decision(
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        intent=intent.name,
        decision=decision,
    )

    if isinstance(pending_workflow, dict) and pending_state in _WORKFLOW_PENDING_STATES:
        if not user_id:
            return _build_response(
                trace_id,
                request_id,
                "needs_auth",
                "민감 작업 확인을 위해 로그인 상태가 필요합니다. 다시 로그인 후 시도해 주세요.",
                reason_code="AUTH_REQUIRED",
                next_action="LOGIN_REQUIRED",
            )
        return await _handle_pending_workflow(
            query,
            pending_workflow,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            request_id=request_id,
        )

    if is_reference_query:
        if not isinstance(selection_state, dict):
            metrics.inc("chat_reference_resolve_total", {"type": "selection", "result": "missing_state"})
            metrics.inc("chat_reference_unresolved_total")
            return _build_response(
                trace_id,
                request_id,
                "needs_input",
                "참조할 추천 목록이 없습니다. 먼저 책 추천을 요청해 주세요.",
                next_action="PROVIDE_REQUIRED_INFO",
            )
        selected, selected_index = _resolve_selection_reference(query, selection_state)
        if selected is None or selected_index is None:
            metrics.inc("chat_reference_resolve_total", {"type": "selection", "result": "unresolved"})
            metrics.inc("chat_reference_unresolved_total")
            return _build_response(
                trace_id,
                request_id,
                "needs_input",
                _render_selection_options(selection_state),
                next_action="PROVIDE_REQUIRED_INFO",
            )
        candidates = selection_state.get("last_candidates") if isinstance(selection_state.get("last_candidates"), list) else []
        _save_selection_state(
            session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
            candidates=[candidate for candidate in candidates if isinstance(candidate, dict)],
            selected_index=selected_index,
        )
        metrics.inc("chat_reference_resolve_total", {"type": "selection", "result": "resolved"})
        return _build_response(
            trace_id,
            request_id,
            "ok",
            _render_selected_candidate(selected, selected_index),
            tool_name="book_selection",
            endpoint="STATE / chat_session_state.selection",
            source_snippet=f"session_id={session_id}, selected_index={selected_index}",
        )

    if decision.route == ROUTE_ANSWER and intent.name == "BOOK_RECOMMEND":
        has_explicit_book_anchor = bool(book_slots.isbn or book_slots.title)
        if is_selection_followup_query and isinstance(selection_state, dict) and not has_explicit_book_anchor:
            seed_candidate = _selection_seed_candidate(selection_state)
            if isinstance(seed_candidate, dict):
                metrics.inc("chat_reference_resolve_total", {"type": "selection_followup", "result": "resolved"})
                return await _handle_book_recommendation(
                    query,
                    session_id=session_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    request_id=request_id,
                    seed_book=seed_candidate,
                    followup_query=query,
                )
            metrics.inc("chat_reference_resolve_total", {"type": "selection_followup", "result": "unresolved"})
            metrics.inc("chat_reference_unresolved_total")

    if intent.name == "NONE":
        return None

    if decision.route == ROUTE_OPTIONS:
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "요청을 정확히 구분하지 못했습니다. 주문/배송/환불/추천 중 어떤 작업인지 알려주세요.",
            reason_code=decision.reason_code,
            next_action="PROVIDE_REQUIRED_INFO",
        )

    if decision.route == ROUTE_ASK and decision.reason_code.startswith("NEED_AUTH:"):
        metrics.inc("chat_tool_authz_denied_total", {"intent": intent.name})
        return _build_response(
            trace_id,
            request_id,
            "needs_auth",
            "주문/배송/환불 조회는 로그인 사용자만 가능합니다. 다시 로그인한 뒤 시도해 주세요.",
            reason_code="AUTH_REQUIRED",
            next_action="LOGIN_REQUIRED",
        )

    if decision.route == ROUTE_ASK and decision.reason_code.startswith("NEED_SLOT:ORDER_REF"):
        action_label = "주문번호(예: ORD20260222XXXX) 또는 주문 ID"
        if intent.name in {"ORDER_CANCEL", "REFUND_CREATE"}:
            return _build_response(
                trace_id,
                request_id,
                "needs_input",
                f"요청을 진행하려면 {action_label}를 먼저 입력해 주세요.",
                reason_code="NEED_SLOT:ORDER_REF",
                next_action="PROVIDE_REQUIRED_INFO",
            )
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            f"조회하려면 {action_label}를 입력해 주세요.",
            reason_code="NEED_SLOT:ORDER_REF",
            next_action="PROVIDE_REQUIRED_INFO",
        )

    if intent.confidence < 0.8 and _is_commerce_related(query):
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "요청을 정확히 구분하지 못했습니다. 주문조회/배송조회/환불조회 중 어떤 도움인지 알려주세요.",
        )

    if decision.route == ROUTE_ANSWER and intent.name == "REFUND_POLICY":
        return _handle_refund_policy_guide(trace_id, request_id)
    if decision.route == ROUTE_ANSWER and intent.name == "SHIPPING_POLICY":
        return _handle_shipping_policy_guide(trace_id, request_id)
    if decision.route == ROUTE_ANSWER and intent.name == "ORDER_POLICY":
        return _handle_order_policy_guide(trace_id, request_id)
    if decision.route == ROUTE_ANSWER and intent.name == "BOOK_RECOMMEND":
        return await _handle_book_recommendation(
            query,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            request_id=request_id,
        )

    if not user_id:
        metrics.inc("chat_tool_authz_denied_total", {"intent": intent.name})
        return _build_response(
            trace_id,
            request_id,
            "needs_auth",
            "주문/배송/환불 조회는 로그인 사용자만 가능합니다. 다시 로그인한 뒤 시도해 주세요.",
        )

    try:
        if decision.route == ROUTE_CONFIRM and intent.name == "ORDER_CANCEL":
            return await _start_sensitive_workflow(
                "ORDER_CANCEL",
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
        if decision.route == ROUTE_CONFIRM and intent.name == "REFUND_CREATE":
            return await _start_sensitive_workflow(
                "REFUND_CREATE",
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
        if intent.name == "TICKET_CREATE":
            return await _handle_ticket_create(
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
                history_issue_context=history_issue_context,
            )
        if intent.name == "TICKET_STATUS":
            return await _handle_ticket_status(
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
        if intent.name == "TICKET_LIST":
            return await _handle_ticket_list(
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
        if intent.name == "ORDER_LOOKUP":
            return await _handle_order_lookup(query, user_id=user_id, trace_id=trace_id, request_id=request_id)
        if intent.name == "SHIPMENT_LOOKUP":
            return await _handle_shipment_lookup(query, user_id=user_id, trace_id=trace_id, request_id=request_id)
        if intent.name == "REFUND_LOOKUP":
            return await _handle_refund_lookup(query, user_id=user_id, trace_id=trace_id, request_id=request_id)
        if intent.name == "CART_RECOMMEND":
            return await _handle_cart_recommendation(
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
    except Exception:
        metrics.inc("chat_tool_fallback_total", {"reason_code": "unexpected_error"})
        return _build_response(
            trace_id,
            request_id,
            "tool_fallback",
            "실시간 커머스 정보를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return None
