import asyncio

import httpx
import pytest

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
    chat_tools._CACHE.set_json(f"chat:fallback:count:{session_id}", {"count": 3}, ttl=600)

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
    assert chat_tools._CACHE.get_json(f"chat:unresolved:{session_id}") == {"cleared": True}
    assert chat_tools._CACHE.get_json(f"chat:fallback:count:{session_id}") == {"count": 0}


def test_run_tool_chat_ticket_create_requires_issue_context():
    session_id = "sess-ticket-ctx-2"
    payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_missing_ctx"))

    assert result is not None
    assert result["status"] == "needs_input"
    assert result["reason_code"] == "MISSING_REQUIRED_INFO"
    assert result["next_action"] == "PROVIDE_REQUIRED_INFO"
    assert "조금 더 자세히" in result["answer"]["content"]


def test_run_tool_chat_ticket_create_is_idempotent_within_dedup_window(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 21,
                    "ticket_no": "STK202602230201",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 180,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-ticket-dedup-1"
    payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 결제가 안돼"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    first = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_1"))
    second = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_2"))

    assert first is not None and first["status"] == "ok"
    assert second is not None and second["status"] == "ok"
    assert "STK202602230201" in second["answer"]["content"]
    assert "재사용" in second["answer"]["content"]
    assert call_count["ticket_create"] == 1


def test_run_tool_chat_ticket_create_dedup_reuse_clears_unresolved_context(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 22,
                    "ticket_no": "STK202602230202",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 60,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    session_id = "sess-ticket-dedup-ctx-1"
    chat_tools._CACHE.set_json(
        f"chat:unresolved:{session_id}",
        {
            "query": "배송이 안와요",
            "reason_code": "PROVIDER_TIMEOUT",
            "trace_id": "trace_prev",
            "request_id": "req_prev",
        },
        ttl=600,
    )
    chat_tools._CACHE.set_json(f"chat:fallback:count:{session_id}", {"count": 2}, ttl=600)

    payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 배송이 안와요"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    first = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_1"))
    second = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_2"))

    assert first is not None and first["status"] == "ok"
    assert second is not None and second["status"] == "ok"
    assert call_count["ticket_create"] == 1
    assert chat_tools._CACHE.get_json(f"chat:unresolved:{session_id}") == {"cleared": True}
    assert chat_tools._CACHE.get_json(f"chat:fallback:count:{session_id}") == {"count": 0}


def test_run_tool_chat_ticket_create_applies_cooldown_for_non_dedup_issue(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 23,
                    "ticket_no": "STK202602230203",
                    "status": "RECEIVED",
                    "severity": "MEDIUM",
                },
                "expected_response_minutes": 90,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    monkeypatch.setattr(chat_tools, "_ticket_create_cooldown_sec", lambda: 60)
    monkeypatch.setattr(chat_tools.time, "time", lambda: 1_700_000_000)

    session_id = "sess-ticket-cooldown-1"
    first_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 결제가 두 번 승인됐어요"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }
    second_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 배송지가 잘못 입력됐어요"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    first = asyncio.run(chat_tools.run_tool_chat(first_payload, "trace_test", "req_create_1"))
    second = asyncio.run(chat_tools.run_tool_chat(second_payload, "trace_test", "req_create_2"))

    assert first is not None and first["status"] == "ok"
    assert second is not None
    assert second["status"] == "needs_input"
    assert second["reason_code"] == "RATE_LIMITED"
    assert second["next_action"] == "RETRY"
    assert second["recoverable"] is True
    assert int(second["retry_after_ms"] or 0) > 0
    assert "다시 시도" in second["answer"]["content"]
    assert call_count["ticket_create"] == 1


def test_build_response_emits_recovery_hint_metric():
    before = dict(chat_tools.metrics.snapshot())
    response = chat_tools._build_response(
        "trace_test",
        "req_test",
        "needs_input",
        "추가 정보가 필요합니다.",
    )
    after = chat_tools.metrics.snapshot()

    key = (
        "chat_error_recovery_hint_total{next_action=PROVIDE_REQUIRED_INFO,"
        "reason_code=MISSING_INPUT,source=tool}"
    )
    assert response["next_action"] == "PROVIDE_REQUIRED_INFO"
    assert after.get(key, 0) >= before.get(key, 0) + 1


def test_call_commerce_timeout_emits_chat_timeout_metric(monkeypatch):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, timeout=None):
            raise httpx.TimeoutException("timeout")

    before = dict(chat_tools.metrics.snapshot())
    monkeypatch.setattr(chat_tools.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(chat_tools, "_tool_lookup_retry_count", lambda: 0)

    with pytest.raises(chat_tools.ToolCallError) as exc_info:
        asyncio.run(
            chat_tools._call_commerce(
                "GET",
                "/orders/12",
                user_id="1",
                trace_id="trace_test",
                request_id="req_test",
                tool_name="order_lookup",
                intent="ORDER_LOOKUP",
            )
        )

    assert exc_info.value.code == "tool_timeout"
    after = chat_tools.metrics.snapshot()
    key = "chat_timeout_total{stage=tool_lookup}"
    assert after.get(key, 0) >= before.get(key, 0) + 1


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
