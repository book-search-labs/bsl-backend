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
