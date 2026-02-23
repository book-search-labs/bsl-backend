import asyncio

from app.core import chat
from app.core import chat_tools


def test_run_tool_chat_requires_login_for_commerce_queries():
    payload = {
        "message": {"role": "user", "content": "주문 12 상태 알려줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_test"))

    assert result is not None
    assert result["status"] == "needs_auth"
    assert result["reason_code"] == "AUTH_REQUIRED"
    assert result["next_action"] == "LOGIN_REQUIRED"
    assert result["recoverable"] is True
    assert "로그인" in result["answer"]["content"]


def test_run_tool_chat_order_lookup_success(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        assert method == "GET"
        assert path == "/orders/12"
        return {
            "order": {
                "order_id": 12,
                "order_no": "ORD202602220001",
                "status": "PAID",
                "total_amount": 33000,
                "shipping_fee": 3000,
                "payment_method": "CARD",
            }
        }

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)

    payload = {
        "message": {"role": "user", "content": "주문 12 상태 알려줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_test"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert result["next_action"] == "NONE"
    assert "ORD202602220001" in result["answer"]["content"]
    assert result["citations"]
    assert result["sources"][0]["url"] == "GET /api/v1/orders/{orderId}"


def test_run_tool_chat_shipment_lookup_without_registered_shipment(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if path == "/orders/12":
            return {
                "order": {
                    "order_id": 12,
                    "order_no": "ORD202602220001",
                    "status": "PAID",
                    "total_amount": 33000,
                    "shipping_fee": 3000,
                    "payment_method": "CARD",
                }
            }
        if path == "/shipments/by-order/12":
            return {"items": []}
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)

    payload = {
        "message": {"role": "user", "content": "배송 상태 확인해줘 주문 12"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_test"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "배송 정보가 등록되지 않았습니다" in result["answer"]["content"]


def test_run_chat_stream_tool_path(monkeypatch):
    async def fake_tool_handler(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "answer": {"role": "assistant", "content": "실시간 주문 정보입니다."},
            "sources": [
                {
                    "citation_key": "tool:order_lookup:1",
                    "doc_id": "tool:order_lookup",
                    "chunk_id": "tool:order_lookup:1",
                    "title": "order_lookup 실시간 조회",
                    "url": "GET /api/v1/orders/{orderId}",
                    "snippet": "order_no=ORD202602220001",
                }
            ],
            "citations": ["tool:order_lookup:1"],
        }

    monkeypatch.setattr(chat, "run_tool_chat", fake_tool_handler)

    async def collect():
        events = []
        async for item in chat.run_chat_stream({"message": {"role": "user", "content": "주문 12"}}, "trace_test", "req_test"):
            events.append(item)
        return events

    events = asyncio.run(collect())

    assert any("event: meta" in event and '"tool_path"' in event for event in events)
    assert any("event: done" in event and '"status": "ok"' in event for event in events)


def test_run_tool_chat_starts_sensitive_cancel_workflow(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        assert method == "GET"
        assert path == "/orders/12"
        return {
            "order": {
                "order_id": 12,
                "order_no": "ORD202602220001",
                "status": "PAID",
                "total_amount": 33000,
                "shipping_fee": 3000,
                "payment_method": "CARD",
            }
        }

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)

    payload = {
        "session_id": "sess-cancel-1",
        "message": {"role": "user", "content": "주문 12 취소해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_test"))

    assert result is not None
    assert result["status"] == "pending_confirmation"
    assert result["reason_code"] == "CONFIRMATION_REQUIRED"
    assert result["next_action"] == "CONFIRM_ACTION"
    assert "확인 코드" in result["answer"]["content"]
    assert result["citations"]


def test_run_tool_chat_executes_cancel_after_confirmation(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/orders/12":
            return {
                "order": {
                    "order_id": 12,
                    "order_no": "ORD202602220001",
                    "status": "PAID",
                    "total_amount": 33000,
                    "shipping_fee": 3000,
                    "payment_method": "CARD",
                }
            }
        if method == "POST" and path == "/orders/12/cancel":
            return {
                "order": {
                    "order_id": 12,
                    "order_no": "ORD202602220001",
                    "status": "CANCELED",
                    "total_amount": 33000,
                    "shipping_fee": 3000,
                    "payment_method": "CARD",
                }
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-cancel-2"
    start_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "주문 12 취소해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    started = asyncio.run(chat_tools.run_tool_chat(start_payload, "trace_test", "req_start"))
    token = started["answer"]["content"].split("[")[1].split("]")[0]

    confirm_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": f"확인 {token}"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    confirmed = asyncio.run(chat_tools.run_tool_chat(confirm_payload, "trace_test", "req_confirm"))

    assert confirmed is not None
    assert confirmed["status"] == "ok"
    assert confirmed["reason_code"] == "OK"
    assert "취소가 완료" in confirmed["answer"]["content"]


def test_run_tool_chat_blocks_when_confirmation_token_is_wrong(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        assert method == "GET"
        assert path == "/orders/12"
        return {
            "order": {
                "order_id": 12,
                "order_no": "ORD202602220001",
                "status": "PAID",
                "total_amount": 33000,
                "shipping_fee": 3000,
                "payment_method": "CARD",
            }
        }

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-cancel-3"
    start_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "주문 12 취소해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    started = asyncio.run(chat_tools.run_tool_chat(start_payload, "trace_test", "req_start"))
    assert started["status"] == "pending_confirmation"

    confirm_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "확인 AAAAAA"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(confirm_payload, "trace_test", "req_confirm"))

    assert result is not None
    assert result["status"] == "pending_confirmation"
    assert "일치하지 않습니다" in result["answer"]["content"]


def test_run_tool_chat_ticket_create_and_status_lookup(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            return {
                "ticket": {
                    "ticket_id": 11,
                    "ticket_no": "STK202602230123",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 240,
            }
        if method == "GET" and path == "/support/tickets/by-number/STK202602230123":
            return {
                "ticket": {
                    "ticket_id": 11,
                    "ticket_no": "STK202602230123",
                    "status": "IN_PROGRESS",
                    "severity": "LOW",
                },
                "expected_response_minutes": 240,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-ticket-1"

    create_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 결제가 안돼"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    created = asyncio.run(chat_tools.run_tool_chat(create_payload, "trace_test", "req_create"))

    assert created is not None
    assert created["status"] == "ok"
    assert "STK202602230123" in created["answer"]["content"]

    status_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "내 문의 상태 알려줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    status_result = asyncio.run(chat_tools.run_tool_chat(status_payload, "trace_test", "req_status"))

    assert status_result is not None
    assert status_result["status"] == "ok"
    assert "처리 중" in status_result["answer"]["content"]


def test_run_tool_chat_ticket_create_uses_unresolved_context(monkeypatch):
    captured = {}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            captured["payload"] = kwargs.get("payload")
            return {
                "ticket": {
                    "ticket_id": 12,
                    "ticket_no": "STK202602230124",
                    "status": "RECEIVED",
                    "severity": "MEDIUM",
                },
                "expected_response_minutes": 120,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-ticket-ctx-1"
    chat_tools._CACHE.set_json(
        f"chat:unresolved:{session_id}",
        {
            "query": "환불 조건을 정리해줘",
            "reason_code": "OUTPUT_GUARD_FORBIDDEN_CLAIM",
            "trace_id": "trace_prev",
            "request_id": "req_prev",
        },
        ttl=600,
    )

    payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_ctx"))

    assert result is not None
    assert result["status"] == "ok"
    assert "직전 실패 사유" in result["answer"]["content"]
    assert captured["payload"]["summary"] == "환불 조건을 정리해줘"
    assert captured["payload"]["details"]["effectiveQuery"] == "환불 조건을 정리해줘"
    assert captured["payload"]["details"]["unresolvedReasonCode"] == "OUTPUT_GUARD_FORBIDDEN_CLAIM"


def test_run_tool_chat_executes_refund_after_confirmation(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/orders/12":
            return {
                "order": {
                    "order_id": 12,
                    "order_no": "ORD202602220001",
                    "status": "DELIVERED",
                    "total_amount": 33000,
                    "shipping_fee": 3000,
                    "payment_method": "CARD",
                }
            }
        if method == "POST" and path == "/refunds":
            return {
                "refund": {
                    "refund_id": 88,
                    "order_id": 12,
                    "status": "REQUESTED",
                    "amount": 30000,
                }
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-refund-1"

    start_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "주문 12 환불 신청해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    started = asyncio.run(chat_tools.run_tool_chat(start_payload, "trace_test", "req_start"))
    token = started["answer"]["content"].split("[")[1].split("]")[0]

    confirm_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": f"확인 {token}"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    confirmed = asyncio.run(chat_tools.run_tool_chat(confirm_payload, "trace_test", "req_confirm"))

    assert confirmed is not None
    assert confirmed["status"] == "ok"
    assert "환불 접수가 완료" in confirmed["answer"]["content"]
