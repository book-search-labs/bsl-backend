from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.metrics import metrics


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
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    citations: list[str] = []
    if tool_name and endpoint and source_snippet:
        sources, citations = _build_tool_source(tool_name, endpoint, source_snippet)
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": status,
        "answer": {"role": "assistant", "content": content},
        "sources": sources,
        "citations": citations,
    }


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


async def run_tool_chat(request: dict[str, Any], trace_id: str, request_id: str) -> dict[str, Any] | None:
    if not _tool_enabled():
        return None

    query = _extract_query_text(request)
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

    user_id = _extract_user_id(request)
    if not user_id:
        metrics.inc("chat_tool_authz_denied_total", {"intent": intent.name})
        return _build_response(
            trace_id,
            request_id,
            "needs_auth",
            "주문/배송/환불 조회는 로그인 사용자만 가능합니다. 다시 로그인한 뒤 시도해 주세요.",
        )

    try:
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
