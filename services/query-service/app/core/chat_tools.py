from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.cache import get_cache
from app.core.metrics import metrics

_CACHE = get_cache()


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


def _workflow_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_WORKFLOW_TTL_SEC", "900")))


def _confirmation_token_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_CONFIRM_TOKEN_TTL_SEC", "300")))


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


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _detect_intent(query: str) -> ToolIntent:
    q = _normalize_text(query)
    if not q:
        return ToolIntent("NONE", 0.0)

    order_ref = _extract_order_ref(query)
    has_order_ref = order_ref.order_id is not None or order_ref.order_no is not None
    has_lookup_word = any(keyword in q for keyword in ["조회", "상태", "확인", "내역", "where", "status", "lookup", "track"])

    shipment_keywords = ["배송", "택배", "출고", "shipment", "tracking"]
    refund_keywords = ["환불", "refund", "반품"]
    order_keywords = ["주문", "order", "결제", "payment"]
    ticket_status_keywords = ["문의 상태", "티켓 상태", "ticket status", "ticket lookup", "내 문의"]
    ticket_create_keywords = ["문의 접수", "티켓 생성", "상담원 연결", "문의 남길", "ticket create", "support ticket"]
    cancel_keywords = ["주문 취소", "취소해", "cancel order", "cancel my order"]
    refund_create_keywords = ["환불 신청", "환불 접수", "refund request", "환불해"]

    if any(keyword in q for keyword in cancel_keywords) and (has_order_ref or "주문" in q or "order" in q):
        return ToolIntent("ORDER_CANCEL", 0.96)
    if any(keyword in q for keyword in refund_create_keywords) and (has_order_ref or "주문" in q or "order" in q):
        return ToolIntent("REFUND_CREATE", 0.95)
    if any(keyword in q for keyword in ticket_status_keywords):
        return ToolIntent("TICKET_STATUS", 0.95)
    if any(keyword in q for keyword in ticket_create_keywords):
        return ToolIntent("TICKET_CREATE", 0.93)

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
    return {
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


def _resolve_session_id(request: dict[str, Any], user_id: str | None) -> str:
    session_id = request.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    if user_id:
        return f"u:{user_id}:default"
    return "anon:default"


def _workflow_cache_key(session_id: str) -> str:
    return f"chat:workflow:{session_id}"


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
    _CACHE.set_json(_workflow_cache_key(session_id), {"state": "cleared"}, ttl=1)


def _last_ticket_cache_key(session_id: str) -> str:
    return f"chat:last-ticket:{session_id}"


def _save_last_ticket_no(session_id: str, ticket_no: str) -> None:
    if ticket_no:
        _CACHE.set_json(_last_ticket_cache_key(session_id), {"ticket_no": ticket_no}, ttl=max(600, _workflow_ttl_sec()))


def _load_last_ticket_no(session_id: str) -> str | None:
    cached = _CACHE.get_json(_last_ticket_cache_key(session_id))
    if not isinstance(cached, dict):
        return None
    value = cached.get("ticket_no")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _unresolved_context_cache_key(session_id: str) -> str:
    return f"chat:unresolved:{session_id}"


def _load_unresolved_context(session_id: str) -> dict[str, Any] | None:
    cached = _CACHE.get_json(_unresolved_context_cache_key(session_id))
    if isinstance(cached, dict):
        return cached
    return None


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


async def _call_commerce(
    method: str,
    path: str,
    *,
    user_id: str,
    trace_id: str,
    request_id: str,
    payload: dict[str, Any] | None = None,
    tool_name: str,
    intent: str,
) -> dict[str, Any]:
    url = f"{_commerce_base_url()}{path}"
    headers = {
        "x-user-id": str(user_id),
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
                raise ToolCallError(code=code, message=message, status_code=response.status_code)

            _record_tool_metrics(intent, tool_name, "ok")
            try:
                return response.json()
            except Exception:
                raise ToolCallError("schema_mismatch", "툴 응답 파싱에 실패했습니다.", status_code=response.status_code)
        except (httpx.TimeoutException, httpx.NetworkError):
            last_error = ToolCallError("tool_timeout", "툴 응답 시간이 초과되었습니다.", status_code=504)
            if attempt < retries:
                await asyncio.sleep(0.12 * (attempt + 1))
                continue
            _record_tool_metrics(intent, tool_name, "timeout")
            metrics.inc("chat_tool_fallback_total", {"reason_code": "tool_timeout"})
            raise last_error
        except ToolCallError as exc:
            last_error = exc
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
    risk = "HIGH"
    workflow = {
        "workflow_id": f"wf:{session_id}:{request_id}",
        "workflow_type": workflow_type,
        "step": "awaiting_confirmation",
        "user_id": user_id,
        "order_id": order_id,
        "order_no": order_no,
        "risk": risk,
        "confirmation_token": token,
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + _confirmation_token_ttl_sec(),
    }
    _save_workflow(session_id, workflow, ttl_sec=_workflow_ttl_sec())
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
) -> dict[str, Any]:
    unresolved = _load_unresolved_context(session_id)
    unresolved_query = str(unresolved.get("query") or "").strip() if isinstance(unresolved, dict) else ""
    unresolved_reason = str(unresolved.get("reason_code") or "").strip() if isinstance(unresolved, dict) else ""
    generic_ticket_request = _is_generic_ticket_create_message(query)
    effective_query = query
    if generic_ticket_request and unresolved_query:
        effective_query = unresolved_query
        metrics.inc("chat_ticket_create_with_context_total", {"source": "unresolved_context"})
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
    _save_last_ticket_no(session_id, ticket_no)
    metrics.inc("chat_ticket_created_total", {"category": category})

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
    ticket_no = _extract_ticket_no(query) or _load_last_ticket_no(session_id)
    if not ticket_no:
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "티켓 상태 조회를 위해 접수번호(예: STK202602230001)를 입력해 주세요.",
        )

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
        if exc.status_code == 403:
            metrics.inc("chat_ticket_authz_denied_total")
            metrics.inc("chat_ticket_status_lookup_total", {"result": "forbidden"})
            return _build_response(trace_id, request_id, "forbidden", "본인 티켓만 조회할 수 있습니다.")
        if exc.code == "not_found":
            metrics.inc("chat_ticket_status_lookup_total", {"result": "not_found"})
            return _build_response(trace_id, request_id, "not_found", "해당 접수번호의 문의를 찾을 수 없습니다.")
        metrics.inc("chat_ticket_status_lookup_total", {"result": "error"})
        return _build_response(trace_id, request_id, "tool_fallback", "티켓 상태를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    ticket = looked_up.get("ticket") if isinstance(looked_up, dict) else {}
    status = str(ticket.get("status") or "RECEIVED")
    status_ko = _ticket_status_ko(status)
    followup = _ticket_followup_message(status)
    metrics.inc("chat_ticket_status_lookup_total", {"result": "ok"})
    metrics.inc("chat_ticket_followup_prompt_total", {"status": status})

    content = f"접수번호 {ticket_no}의 현재 상태는 '{status_ko}'입니다. {followup}"
    return _build_response(
        trace_id,
        request_id,
        "ok",
        content,
        tool_name="ticket_status_lookup",
        endpoint="GET /api/v1/support/tickets/by-number/{ticketNo}",
        source_snippet=f"ticket_no={ticket_no}, status={status}",
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
    order_id = int(workflow.get("order_id"))
    order_no = str(workflow.get("order_no") or f"#{order_id}")

    try:
        if workflow_type == "ORDER_CANCEL":
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
            _clear_workflow(session_id)
            metrics.inc("chat_sensitive_action_confirmed_total", {"action": "order_cancel"})
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "success"})
            return _build_response(
                trace_id,
                request_id,
                "ok",
                f"주문 {order_no} 취소가 완료되었습니다. 현재 상태는 '{status}'입니다.",
                tool_name="order_cancel",
                endpoint="POST /api/v1/orders/{orderId}/cancel",
                source_snippet=f"order_no={order_no}, status={status}",
            )

        if workflow_type == "REFUND_CREATE":
            refund_result = await _call_commerce(
                "POST",
                "/refunds",
                payload={
                    "orderId": order_id,
                    "reasonCode": "OTHER",
                    "reasonText": "CHAT_REQUEST",
                    "idempotencyKey": f"chat-refund-{request_id}",
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
            _clear_workflow(session_id)
            metrics.inc("chat_sensitive_action_confirmed_total", {"action": "refund_create"})
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "success"})
            return _build_response(
                trace_id,
                request_id,
                "ok",
                f"주문 {order_no} 환불 접수가 완료되었습니다. 접수번호는 {refund_id}, 상태는 '{refund_status}', 예상 환불 금액은 {refund_amount}입니다.",
                tool_name="refund_create",
                endpoint="POST /api/v1/refunds",
                source_snippet=f"order_no={order_no}, refund_id={refund_id}, status={refund_status}",
            )
    except ToolCallError as exc:
        metrics.inc("chat_workflow_step_error_total", {"type": workflow_type, "step": "execute", "error_code": exc.code})
        if exc.status_code == 403:
            metrics.inc("chat_sensitive_action_blocked_total", {"reason": "authz_denied"})
            _clear_workflow(session_id)
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "blocked"})
            return _build_response(trace_id, request_id, "forbidden", "본인 주문만 처리할 수 있습니다.")
        if exc.code == "invalid_state":
            _clear_workflow(session_id)
            metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "invalid_state"})
            return _build_response(trace_id, request_id, "invalid_state", "현재 주문 상태에서는 요청한 작업을 진행할 수 없습니다.")
        return _build_response(trace_id, request_id, "tool_fallback", "작업 실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    metrics.inc("chat_workflow_step_error_total", {"type": workflow_type, "step": "execute", "error_code": "unsupported"})
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

    if expected_user_id and expected_user_id != str(user_id):
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "user_mismatch"})
        _clear_workflow(session_id)
        return _build_response(trace_id, request_id, "forbidden", "다른 사용자 세션의 작업은 확인할 수 없습니다.")

    expires_at = int(workflow.get("expires_at") or 0)
    if expires_at > 0 and int(time.time()) > expires_at:
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "confirmation_expired"})
        _clear_workflow(session_id)
        metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "expired"})
        return _build_response(trace_id, request_id, "expired", "확인 코드가 만료되어 요청이 취소되었습니다. 다시 요청해 주세요.")

    if _is_abort_message(query) and "확인" not in _normalize_text(query):
        _clear_workflow(session_id)
        metrics.inc("chat_sensitive_action_blocked_total", {"reason": "user_aborted"})
        metrics.inc("chat_workflow_completed_total", {"type": workflow_type, "result": "aborted"})
        return _build_response(trace_id, request_id, "aborted", "요청하신 작업을 취소했습니다.")

    if not _is_confirmation_message(query):
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

    if user_id:
        pending_workflow = _load_workflow(session_id)
        if pending_workflow is not None and str(pending_workflow.get("step") or "") == "awaiting_confirmation":
            return await _handle_pending_workflow(
                query,
                pending_workflow,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )

    intent = _detect_intent(query)
    if intent.name == "NONE":
        return None

    if intent.confidence < 0.8 and _is_commerce_related(query):
        return _build_response(
            trace_id,
            request_id,
            "needs_input",
            "요청을 정확히 구분하지 못했습니다. 주문조회/배송조회/환불조회 중 어떤 도움인지 알려주세요.",
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
        if intent.name == "ORDER_CANCEL":
            return await _start_sensitive_workflow(
                "ORDER_CANCEL",
                query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                request_id=request_id,
            )
        if intent.name == "REFUND_CREATE":
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
            )
        if intent.name == "TICKET_STATUS":
            return await _handle_ticket_status(
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
    except Exception:
        metrics.inc("chat_tool_fallback_total", {"reason_code": "unexpected_error"})
        return _build_response(
            trace_id,
            request_id,
            "tool_fallback",
            "실시간 커머스 정보를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return None
