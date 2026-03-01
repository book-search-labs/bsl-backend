import asyncio

import httpx
import pytest

from app.core import chat
from app.core import chat_tools
from app.core.cache import CacheClient
from app.core.metrics import metrics


@pytest.fixture(autouse=True)
def _disable_ticket_create_cooldown_by_default(monkeypatch):
    monkeypatch.setattr(chat_tools, "_ticket_create_cooldown_sec", lambda: 0)


@pytest.fixture(autouse=True)
def _clear_chat_tools_cache():
    cache_obj = chat_tools._CACHE
    local = getattr(cache_obj, "_local", None)
    store = getattr(local, "_store", None)
    if isinstance(store, dict):
        store.clear()


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


def test_run_tool_chat_refund_policy_guide_without_login():
    payload = {
        "message": {"role": "user", "content": "환불 조건을 정리해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_refund_policy"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "환불/반품 조건" in result["answer"]["content"]
    assert "주문번호를 알려주시면" in result["answer"]["content"]
    assert result["citations"]
    assert result["sources"][0]["url"] == "POLICY / commerce-refund-guide"


def test_run_tool_chat_shipping_policy_guide_without_login():
    payload = {
        "message": {"role": "user", "content": "배송비 기준 안내해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_shipping_policy"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "배송 정책" in result["answer"]["content"]
    assert "기본 배송비" in result["answer"]["content"]
    assert result["citations"]
    assert result["sources"][0]["url"] == "POLICY / commerce-shipping-guide"


def test_detect_intent_routes_refund_possibility_to_policy():
    intent = chat_tools._detect_intent("환불 가능해?")
    assert intent.name == "REFUND_POLICY"


def test_detect_intent_routes_order_cancel_question_to_policy():
    intent = chat_tools._detect_intent("주문 취소 가능한가요?")
    assert intent.name == "ORDER_POLICY"


def test_policy_topic_cache_key_normalizes_aliases():
    refund_key = chat_tools._policy_topic_cache_key("refund")
    assert refund_key == chat_tools._policy_topic_cache_key("refund_policy")
    assert refund_key == chat_tools._policy_topic_cache_key("환불")


def test_refund_policy_topic_cache_reuses_composed_content(monkeypatch):
    compose_calls = {"count": 0}

    def fake_base_fee():
        compose_calls["count"] += 1
        return 3000

    monkeypatch.setattr(chat_tools, "_policy_base_shipping_fee", fake_base_fee)
    monkeypatch.setattr(chat_tools, "_policy_fast_shipping_fee", lambda: 5000)
    monkeypatch.setattr(chat_tools, "_policy_free_shipping_threshold", lambda: 20000)

    first = chat_tools._handle_refund_policy_guide("trace_test", "req_refund_policy_cache_1")
    second = chat_tools._handle_refund_policy_guide("trace_test", "req_refund_policy_cache_2")

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert compose_calls["count"] == 1
    assert first["answer"]["content"] == second["answer"]["content"]


def test_run_tool_chat_book_recommendation_without_login(monkeypatch):
    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        assert query in {"周易辭典", "도서 '周易辭典' 기준으로 비슷한 책을 추천해줘"}
        return [
            {"doc_id": "nlk:CM0000000201", "title": "周易辭典", "author": "장선문", "score": 8.4},
            {"doc_id": "nlk:CM0000000302", "title": "中國民間宗教史", "author": "마시사", "score": 7.8},
            {"doc_id": "nlk:CM0000000411", "title": "馬列主義與宗敎的衝突", "author": "왕장링", "score": 7.5},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)

    payload = {
        "message": {"role": "user", "content": "도서 '周易辭典' 기준으로 비슷한 책을 추천해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_book_recommend"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "周易辭典" in result["answer"]["content"]
    assert "中國民間宗教史" in result["answer"]["content"]
    assert "馬列主義與宗敎的衝突" in result["answer"]["content"]
    assert "추천 이유:" in result["answer"]["content"]
    assert "다음으로 진행할 수 있어요" in result["answer"]["content"]
    assert result["citations"]
    assert result["sources"][0]["url"] == "OS /books_doc_read/_search"


def test_run_tool_chat_book_recommendation_uses_normalized_isbn_seed(monkeypatch):
    captured = {"queries": [], "standalone_query": None, "slots": None}
    real_build_understanding = chat_tools.build_understanding

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        captured["queries"].append(query)
        return [
            {"doc_id": "doc-seed", "title": "시드 도서", "author": "저자A", "isbn": "978-0-306-40615-7", "score": 0.99},
            {"doc_id": "doc-b", "title": "비슷한 도서 B", "author": "저자B", "isbn": "9780306406158", "score": 0.82},
        ]

    def spy_build_understanding(*, query, intent, slots, standalone_query=None, risk_level=None, q_key=None):
        captured["standalone_query"] = standalone_query
        captured["slots"] = slots
        return real_build_understanding(
            query=query,
            intent=intent,
            slots=slots,
            standalone_query=standalone_query,
            risk_level=risk_level,
            q_key=q_key,
        )

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)
    monkeypatch.setattr(chat_tools, "build_understanding", spy_build_understanding)

    payload = {
        "message": {"role": "user", "content": "ISBN 978-0-306-40615-7 기준으로 비슷한 책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_book_recommend_isbn"))

    assert result is not None
    assert result["status"] == "ok"
    assert captured["queries"]
    assert captured["queries"][0] == "9780306406157"
    assert captured["standalone_query"] == "9780306406157"
    assert captured["slots"]["book_query"]["isbn"] == "9780306406157"
    assert "1) 시드 도서" not in result["answer"]["content"]
    assert "비슷한 도서 B" in result["answer"]["content"]


def test_run_tool_chat_book_recommendation_persists_selection_state(monkeypatch):
    captured = {}

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        return [
            {"doc_id": "doc-1", "title": "추천 도서 A", "author": "저자A", "score": 0.91},
            {"doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "score": 0.82},
        ]

    def fake_upsert_session_state(conversation_id, **kwargs):
        captured["conversation_id"] = conversation_id
        captured["selection"] = kwargs.get("selection")
        return {"selection": kwargs.get("selection")}

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)
    monkeypatch.setattr(chat_tools, "upsert_session_state", fake_upsert_session_state)

    payload = {
        "session_id": "sess-reco-1",
        "message": {"role": "user", "content": "책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_reco_1"))

    assert result is not None
    assert result["status"] == "ok"
    assert captured["conversation_id"] == "sess-reco-1"
    assert isinstance(captured["selection"], dict)
    assert captured["selection"]["type"] == "BOOK_RECOMMENDATION"
    assert len(captured["selection"]["last_candidates"]) >= 2


def test_build_selection_candidates_normalizes_book_metadata():
    candidates = chat_tools._build_selection_candidates(
        [
            {
                "doc_id": "doc-1",
                "title": "추천 도서 A",
                "author": "저자A",
                "isbn": "978-0-306-40615-7",
                "series": "시리즈A",
                "volume": "2",
                "format": "전자책",
            }
        ]
    )

    assert len(candidates) == 1
    first = candidates[0]
    assert first["isbn"] == "9780306406157"
    assert first["series"] == "시리즈A"
    assert first["volume"] == 2
    assert first["format"] == "ebook"


def test_run_tool_chat_resolves_second_reference_from_selection_state(monkeypatch):
    persisted = {}

    monkeypatch.setattr(
        chat_tools,
        "get_durable_chat_session_state",
        lambda session_id: {
            "selection": {
                "type": "BOOK_RECOMMENDATION",
                "last_candidates": [
                    {"index": 1, "doc_id": "doc-1", "title": "추천 도서 A", "author": "저자A"},
                    {"index": 2, "doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B"},
                ],
                "selected_index": None,
                "selected_book": None,
            }
        },
    )

    def fake_upsert_session_state(conversation_id, **kwargs):
        persisted["conversation_id"] = conversation_id
        persisted["selection"] = kwargs.get("selection")
        return {"selection": kwargs.get("selection")}

    monkeypatch.setattr(chat_tools, "upsert_session_state", fake_upsert_session_state)

    payload = {
        "session_id": "sess-reco-2",
        "message": {"role": "user", "content": "2번째로 할게"},
        "client": {"locale": "ko-KR"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_reco_2"))

    assert result is not None
    assert result["status"] == "ok"
    assert "2번째로 선택하신 도서" in result["answer"]["content"]
    assert "추천 도서 B" in result["answer"]["content"]
    assert persisted["selection"]["selected_index"] == 2


def test_run_tool_chat_recommend_followup_uses_selected_seed(monkeypatch):
    captured_queries = []

    monkeypatch.setattr(
        chat_tools,
        "get_durable_chat_session_state",
        lambda session_id: {
            "selection": {
                "type": "BOOK_RECOMMENDATION",
                "last_candidates": [
                    {"index": 1, "doc_id": "doc-1", "title": "추천 도서 A", "author": "저자A", "isbn": "9780306406157"},
                    {"index": 2, "doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158"},
                ],
                "selected_index": 2,
                "selected_book": {"index": 2, "doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158"},
            }
        },
    )

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        captured_queries.append(query)
        return [
            {"doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158", "score": 0.93},
            {"doc_id": "doc-3", "title": "다른 출판사 도서", "author": "저자C", "score": 0.81},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)

    payload = {
        "session_id": "sess-reco-followup-1",
        "message": {"role": "user", "content": "다른 출판사 책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_reco_followup_1"))

    assert result is not None
    assert result["status"] == "ok"
    assert captured_queries
    assert captured_queries[0] == "추천 도서 B 다른 출판사 책 추천해줘"
    assert "1) 추천 도서 B" not in result["answer"]["content"]
    assert "다른 출판사 도서" in result["answer"]["content"]
    assert "출판사 다양화 요청" in result["answer"]["content"]


def test_run_tool_chat_recommend_followup_easier_version_uses_selected_seed(monkeypatch):
    captured_queries = []

    monkeypatch.setattr(
        chat_tools,
        "get_durable_chat_session_state",
        lambda session_id: {
            "selection": {
                "type": "BOOK_RECOMMENDATION",
                "last_candidates": [
                    {"index": 1, "doc_id": "doc-1", "title": "추천 도서 A", "author": "저자A", "isbn": "9780306406157"},
                    {"index": 2, "doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158"},
                ],
                "selected_index": 2,
                "selected_book": {"index": 2, "doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158"},
            }
        },
    )

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        captured_queries.append(query)
        return [
            {"doc_id": "doc-2", "title": "추천 도서 B", "author": "저자B", "isbn": "9780306406158", "score": 0.94},
            {"doc_id": "doc-easy", "title": "추천 도서 B 입문", "author": "저자D", "score": 0.83},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)

    payload = {
        "session_id": "sess-reco-followup-2",
        "message": {"role": "user", "content": "더 쉬운 버전 책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_reco_followup_2"))

    assert result is not None
    assert result["status"] == "ok"
    assert captured_queries
    assert captured_queries[0] == "추천 도서 B 더 쉬운 버전 책 추천해줘"
    assert "1) 추천 도서 B (" not in result["answer"]["content"]
    assert "추천 도서 B 입문" in result["answer"]["content"]
    assert "난이도 완화 요청" in result["answer"]["content"]


def test_run_tool_chat_reference_without_selection_state_returns_needs_input(monkeypatch):
    monkeypatch.setattr(chat_tools, "get_durable_chat_session_state", lambda session_id: None)

    payload = {
        "session_id": "sess-reco-3",
        "message": {"role": "user", "content": "그거 추천해줘"},
        "client": {"locale": "ko-KR"},
    }
    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_reco_3"))

    assert result is not None
    assert result["status"] == "needs_input"
    assert result["reason_code"] == "MISSING_INPUT"
    assert "추천 목록이 없습니다" in result["answer"]["content"]


def test_run_tool_chat_cart_recommendation_with_login(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        assert method == "GET"
        assert path == "/cart"
        return {
            "cart": {
                "items": [
                    {"title": "초등영어교육의 영미문화지도에 관한 연구"},
                    {"title": "周易辭典"},
                ]
            }
        }

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        if query == "초등영어교육의 영미문화지도에 관한 연구":
            return [
                {"doc_id": "nlk:CDM200900003", "title": "초등영어교육의 영미문화지도에 관한 연구", "author": "한은경", "score": 9.1},
                {"doc_id": "nlk:CDM201100017", "title": "영미문화 교육론", "author": "박민정", "score": 8.2},
            ]
        if query == "周易辭典":
            return [
                {"doc_id": "nlk:CM0000000201", "title": "周易辭典", "author": "장선문", "score": 8.4},
                {"doc_id": "nlk:CM0000000302", "title": "中國民間宗教史", "author": "마시사", "score": 7.8},
            ]
        return []

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)

    payload = {
        "message": {"role": "user", "content": "장바구니 기준 추천해줘"},
        "client": {"locale": "ko-KR", "user_id": "1"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_cart_recommend"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "장바구니 도서를 기준으로 추천 도서를 정리했습니다." in result["answer"]["content"]
    assert "영미문화 교육론" in result["answer"]["content"]
    assert "中國民間宗教史" in result["answer"]["content"]
    assert "추천 이유:" in result["answer"]["content"]
    assert "다음으로 진행할 수 있어요" in result["answer"]["content"]
    assert result["citations"]
    assert result["sources"][0]["url"] == "GET /api/v1/cart"


def test_run_tool_chat_book_recommendation_excludes_same_seed_only(monkeypatch):
    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        return [
            {"doc_id": "nlk:CM0000000201", "title": "周易辭典", "author": "장선문", "score": 8.4},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)

    payload = {
        "message": {"role": "user", "content": "도서 '周易辭典' 기준으로 비슷한 책을 추천해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_book_recommend_same_only"))

    assert result is not None
    assert result["status"] == "ok"
    assert result["reason_code"] == "OK"
    assert "동일 도서 외 유사 후보를 찾지 못했습니다." in result["answer"]["content"]
    assert "周易辭典 (장선문 / nlk:CM0000000201)" not in result["answer"]["content"]


def test_run_tool_chat_book_recommendation_experiment_diversity_variant(monkeypatch):
    monkeypatch.setenv("QS_CHAT_RECOMMEND_EXPERIMENT_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_EXPERIMENT_DIVERSITY_PERCENT", "100")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_QUALITY_MIN_CANDIDATES", "1")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_QUALITY_MIN_DIVERSITY", "2")

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        return [
            {"doc_id": "seed-1", "title": "시드 도서", "author": "저자S", "score": 0.99},
            {"doc_id": "doc-a1", "title": "추천 도서 A1", "author": "저자A", "score": 0.95},
            {"doc_id": "doc-a2", "title": "추천 도서 A2", "author": "저자A", "score": 0.94},
            {"doc_id": "doc-b1", "title": "추천 도서 B1", "author": "저자B", "score": 0.80},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)
    served_metric = "chat_recommend_experiment_total{status=served,variant=diversity}"
    before_served = int(metrics.snapshot().get(served_metric, 0))

    payload = {
        "session_id": "sess-reco-exp-diversity",
        "message": {"role": "user", "content": "도서 '시드 도서' 기준으로 비슷한 책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_book_recommend_exp_div"))

    assert result is not None
    assert result["status"] == "ok"
    content = result["answer"]["content"]
    assert "선정 근거:" in content
    assert content.index("추천 도서 A1") < content.index("추천 도서 B1")
    assert content.index("추천 도서 B1") < content.index("추천 도서 A2")
    assert int(metrics.snapshot().get(served_metric, 0)) >= before_served + 1


def test_run_tool_chat_book_recommendation_experiment_quality_gate_blocks_variant(monkeypatch):
    monkeypatch.setenv("QS_CHAT_RECOMMEND_EXPERIMENT_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_EXPERIMENT_DIVERSITY_PERCENT", "100")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_QUALITY_MIN_CANDIDATES", "2")
    monkeypatch.setenv("QS_CHAT_RECOMMEND_QUALITY_MIN_DIVERSITY", "3")

    async def fake_retrieve_candidates(query, trace_id, request_id, top_k=None):
        return [
            {"doc_id": "seed-1", "title": "시드 도서", "author": "저자S", "score": 0.99},
            {"doc_id": "doc-a1", "title": "추천 도서 A1", "author": "저자A", "score": 0.95},
            {"doc_id": "doc-a2", "title": "추천 도서 A2", "author": "저자A", "score": 0.94},
        ]

    monkeypatch.setattr(chat_tools, "retrieve_candidates", fake_retrieve_candidates)
    block_metric = "chat_recommend_quality_gate_block_total{reason=low_diversity}"
    blocked_variant_metric = "chat_recommend_experiment_total{status=blocked,variant=diversity}"
    before_block = int(metrics.snapshot().get(block_metric, 0))
    before_blocked_variant = int(metrics.snapshot().get(blocked_variant_metric, 0))

    payload = {
        "session_id": "sess-reco-exp-gate",
        "message": {"role": "user", "content": "도서 '시드 도서' 기준으로 비슷한 책 추천해줘"},
        "client": {"locale": "ko-KR"},
    }

    result = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_book_recommend_exp_gate"))

    assert result is not None
    assert result["status"] == "ok"
    content = result["answer"]["content"]
    assert "추천 이유:" in content
    assert "선정 근거:" not in content
    assert int(metrics.snapshot().get(block_metric, 0)) >= before_block + 1
    assert int(metrics.snapshot().get(blocked_variant_metric, 0)) >= before_blocked_variant + 1


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


def test_run_tool_chat_starts_sensitive_workflow_with_action_draft_and_fsm(monkeypatch):
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
    session_id = "sess-cancel-fsm-1"
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "주문 12 취소해줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_fsm_start",
        )
    )

    assert result is not None
    assert result["status"] == "pending_confirmation"
    workflow = chat_tools._load_workflow(session_id)
    assert isinstance(workflow, dict)
    assert workflow.get("fsm_state") == "AWAITING_CONFIRMATION"
    action_draft = workflow.get("action_draft")
    assert isinstance(action_draft, dict)
    assert action_draft.get("action_type") == "ORDER_CANCEL"
    assert str(action_draft.get("idempotency_key") or "").startswith("chat:order_cancel:")


def test_execute_sensitive_workflow_blocks_without_confirm_state():
    workflow = {
        "workflow_id": "wf:test",
        "workflow_type": "ORDER_CANCEL",
        "order_id": 12,
        "order_no": "ORD202602220001",
        "fsm_state": "AWAITING_CONFIRMATION",
        "action_draft": chat_tools.build_action_draft(
            action_type="ORDER_CANCEL",
            args={"order_id": 12, "order_no": "ORD202602220001"},
            conversation_id="sess-confirm-block",
            user_id="1",
            tenant_id="books",
            trace_id="trace_test",
            request_id="req_block",
            confirm_ttl_sec=300,
        ),
    }

    result = asyncio.run(
        chat_tools._execute_sensitive_workflow(
            workflow,
            user_id="1",
            session_id="sess-confirm-block",
            trace_id="trace_test",
            request_id="req_block",
        )
    )

    assert result["status"] == "pending_confirmation"
    assert result["reason_code"] == "DENY_EXECUTE:NOT_CONFIRMED"


def test_execute_sensitive_workflow_sets_retryable_state_on_timeout(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        raise chat_tools.ToolCallError("tool_timeout", "timeout", status_code=504)

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    workflow = {
        "workflow_id": "wf:retry",
        "workflow_type": "ORDER_CANCEL",
        "order_id": 12,
        "order_no": "ORD202602220001",
        "fsm_state": "CONFIRMED",
        "retry_count": 0,
        "max_retry": 1,
        "action_draft": chat_tools.build_action_draft(
            action_type="ORDER_CANCEL",
            args={"order_id": 12, "order_no": "ORD202602220001"},
            conversation_id="sess-retry",
            user_id="1",
            tenant_id="books",
            trace_id="trace_test",
            request_id="req_retry",
            confirm_ttl_sec=300,
        ),
    }

    result = asyncio.run(
        chat_tools._execute_sensitive_workflow(
            workflow,
            user_id="1",
            session_id="sess-retry",
            trace_id="trace_test",
            request_id="req_retry",
        )
    )

    assert result["status"] == "tool_fallback"
    assert result["reason_code"] == "TOOL_RETRYABLE_FAILURE"
    assert workflow.get("fsm_state") == "FAILED_RETRYABLE"


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


def test_run_tool_chat_records_policy_decision_audit(monkeypatch):
    audit_calls = []

    monkeypatch.setattr(chat_tools, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-policy-audit-1",
                "message": {"role": "user", "content": "환불 조건을 정리해줘"},
                "client": {"locale": "ko-KR"},
            },
            "trace_test",
            "req_policy_audit",
        )
    )

    assert result is not None
    assert result["status"] == "ok"
    assert any(call.get("action_type") == "POLICY_DECISION" for call in audit_calls)


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


def test_run_tool_chat_ticket_status_lookup_with_ticket_number_only(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_call_commerce(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == "/support/tickets/by-number/STK202602230777":
            return {
                "ticket": {
                    "ticket_id": 777,
                    "ticket_no": "STK202602230777",
                    "status": "IN_PROGRESS",
                    "category": "GENERAL",
                    "severity": "LOW",
                },
                "expected_response_minutes": 70,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-number-only-1",
                "message": {"role": "user", "content": "STK202602230777 확인해줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_ticket_number_only",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230777" in result["answer"]["content"]
    assert calls == [
        ("GET", "/support/tickets/by-number/STK202602230777"),
        ("GET", "/support/tickets/777/events"),
    ]
    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_cache_key("sess-ticket-number-only-1")) == {
        "ticket_no": "STK202602230777",
        "user_id": "1",
    }
    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_user_cache_key("1")) == {"ticket_no": "STK202602230777"}
    assert after_metrics.get("chat_ticket_status_lookup_ticket_source_total{source=query}", 0) >= before_metrics.get(
        "chat_ticket_status_lookup_ticket_source_total{source=query}",
        0,
    ) + 1


def test_run_tool_chat_ticket_list_success(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_call_commerce(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == "/support/tickets?limit=3":
            return {
                "items": [
                    {
                        "ticket_no": "STK202602230601",
                        "status": "IN_PROGRESS",
                        "category": "REFUND",
                        "severity": "HIGH",
                    },
                    {
                        "ticket_no": "STK202602230600",
                        "status": "RECEIVED",
                        "category": "SHIPPING",
                        "severity": "MEDIUM",
                    },
                ]
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-list-1",
                "message": {"role": "user", "content": "내 문의 내역 3건 보여줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_ticket_list_ok",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    content = result["answer"]["content"]
    assert "최근 문의 내역" in content
    assert "STK202602230601" in content
    assert "환불/반품" in content
    assert "긴급" in content
    assert calls == [("GET", "/support/tickets?limit=3")]
    assert result["sources"][0]["url"] == "GET /api/v1/support/tickets"
    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_cache_key("sess-ticket-list-1")) == {
        "ticket_no": "STK202602230601",
        "user_id": "1",
    }
    assert after_metrics.get("chat_ticket_list_total{result=ok}", 0) >= before_metrics.get(
        "chat_ticket_list_total{result=ok}",
        0,
    ) + 1


def test_run_tool_chat_ticket_list_empty(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/support/tickets?limit=5":
            return {"items": []}
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-list-empty-1",
                "message": {"role": "user", "content": "문의 목록 보여줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_ticket_list_empty",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    assert "접수된 문의 내역이 없습니다" in result["answer"]["content"]
    assert after_metrics.get("chat_ticket_list_total{result=empty}", 0) >= before_metrics.get(
        "chat_ticket_list_total{result=empty}",
        0,
    ) + 1


def test_run_tool_chat_ticket_list_parses_english_limit(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_call_commerce(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == "/support/tickets?limit=7":
            return {"items": []}
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-list-en-limit-1",
                "message": {"role": "user", "content": "show my tickets 7 items"},
                "client": {"locale": "en-US", "user_id": "1"},
            },
            "trace_test",
            "req_ticket_list_en_limit",
        )
    )

    assert result is not None
    assert result["status"] == "ok"
    assert calls == [("GET", "/support/tickets?limit=7")]


def test_run_tool_chat_ticket_status_lookup_uses_recent_ticket_list_when_no_reference(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_call_commerce(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == "/support/tickets?limit=1":
            return {
                "items": [
                    {
                        "ticket_id": 41,
                        "ticket_no": "STK202602230401",
                        "status": "IN_PROGRESS",
                    }
                ]
            }
        if method == "GET" and path == "/support/tickets/by-number/STK202602230401":
            return {
                "ticket": {
                    "ticket_id": 41,
                    "ticket_no": "STK202602230401",
                    "status": "IN_PROGRESS",
                    "severity": "LOW",
                },
                "expected_response_minutes": 60,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-list-1",
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_status_from_list",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230401" in result["answer"]["content"]
    assert "처리 중" in result["answer"]["content"]
    assert calls == [
        ("GET", "/support/tickets?limit=1"),
        ("GET", "/support/tickets/by-number/STK202602230401"),
        ("GET", "/support/tickets/41/events"),
    ]
    metric_key = "chat_ticket_status_lookup_ticket_source_total{source=list}"
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1


def test_run_tool_chat_ticket_status_lookup_needs_input_when_no_recent_ticket(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/support/tickets?limit=1":
            return {"items": []}
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-list-empty-1",
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_status_list_empty",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "needs_input"
    assert "최근 접수된 문의가 없습니다" in result["answer"]["content"]
    assert after_metrics.get("chat_ticket_status_lookup_total{result=needs_input}", 0) >= before_metrics.get(
        "chat_ticket_status_lookup_total{result=needs_input}",
        0,
    ) + 1
    assert after_metrics.get("chat_ticket_status_lookup_ticket_source_total{source=missing}", 0) >= before_metrics.get(
        "chat_ticket_status_lookup_ticket_source_total{source=missing}",
        0,
    ) + 1


def test_run_tool_chat_ticket_status_lookup_returns_needs_input_when_recent_lookup_errors(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/support/tickets?limit=1":
            raise chat_tools.ToolCallError("tool_timeout", "timeout", status_code=504)
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-list-error-1",
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_status_list_error",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "needs_input"
    assert "최근 문의 내역을 조회하지 못했습니다" in result["answer"]["content"]
    assert after_metrics.get("chat_ticket_status_lookup_total{result=recent_lookup_error}", 0) >= before_metrics.get(
        "chat_ticket_status_lookup_total{result=recent_lookup_error}",
        0,
    ) + 1
    assert after_metrics.get("chat_ticket_status_recent_lookup_total{result=error}", 0) >= before_metrics.get(
        "chat_ticket_status_recent_lookup_total{result=error}",
        0,
    ) + 1


def test_run_tool_chat_ticket_status_lookup_recovers_when_cached_ticket_is_stale(monkeypatch):
    calls: list[tuple[str, str]] = []
    session_id = "sess-ticket-status-recover-1"
    user_id = "ticket-status-recover-user-1"
    chat_tools._CACHE.set_json(
        chat_tools._last_ticket_cache_key(session_id),
        {"ticket_no": "STK202602230499", "user_id": user_id},
        ttl=300,
    )

    async def fake_call_commerce(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == "/support/tickets/by-number/STK202602230499":
            raise chat_tools.ToolCallError("not_found", "not found", status_code=404)
        if method == "GET" and path == "/support/tickets?limit=1":
            return {"items": [{"ticket_no": "STK202602230500"}]}
        if method == "GET" and path == "/support/tickets/by-number/STK202602230500":
            return {
                "ticket": {
                    "ticket_id": 50,
                    "ticket_no": "STK202602230500",
                    "status": "IN_PROGRESS",
                    "severity": "LOW",
                },
                "expected_response_minutes": 80,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_status_cache_recover",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230500" in result["answer"]["content"]
    assert "처리 중" in result["answer"]["content"]
    assert calls == [
        ("GET", "/support/tickets/by-number/STK202602230499"),
        ("GET", "/support/tickets?limit=1"),
        ("GET", "/support/tickets/by-number/STK202602230500"),
        ("GET", "/support/tickets/50/events"),
    ]
    assert after_metrics.get("chat_ticket_status_lookup_cache_recovery_total{result=recovered}", 0) >= before_metrics.get(
        "chat_ticket_status_lookup_cache_recovery_total{result=recovered}",
        0,
    ) + 1


def test_run_tool_chat_ticket_status_lookup_includes_category_severity_and_eta(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/support/tickets?limit=1":
            return {"items": [{"ticket_no": "STK202602230511"}]}
        if method == "GET" and path == "/support/tickets/by-number/STK202602230511":
            return {
                "ticket": {
                    "ticket_id": 511,
                    "ticket_no": "STK202602230511",
                    "status": "RECEIVED",
                    "category": "REFUND",
                    "severity": "HIGH",
                },
                "expected_response_minutes": 45,
            }
        if method == "GET" and path == "/support/tickets/511/events":
            return {
                "items": [
                    {
                        "event_type": "TICKET_RECEIVED",
                        "note": "ticket created",
                        "created_at": "2026-02-24T11:20:30",
                    },
                    {
                        "event_type": "STATUS_CHANGED",
                        "note": "담당자 배정",
                        "created_at": "2026-02-24T11:30:00",
                    },
                ]
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-enriched-1",
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_status_enriched",
        )
    )

    assert result is not None
    assert result["status"] == "ok"
    content = result["answer"]["content"]
    assert "환불/반품" in content
    assert "긴급" in content
    assert "45분" in content
    assert "최근 처리 이력" in content
    assert "상태 변경" in content
    assert "담당자 배정" in content


def test_save_last_ticket_no_respects_configured_ttl(monkeypatch):
    chat_tools._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_LAST_TICKET_TTL_SEC", "7200")
    monkeypatch.setattr(chat_tools.time, "time", lambda: 1_700_200_000)

    session_id = "sess-last-ticket-ttl-1"
    user_id = "last-ticket-ttl-user-1"
    chat_tools._save_last_ticket_no(session_id, user_id, "STK202602230399")

    local_store = chat_tools._CACHE._local._store
    session_entry = local_store.get(chat_tools._last_ticket_cache_key(session_id))
    user_entry = local_store.get(chat_tools._last_ticket_user_cache_key(user_id))

    assert session_entry is not None
    assert user_entry is not None
    assert session_entry[0] == 1_700_207_200
    assert user_entry[0] == 1_700_207_200


def test_load_last_ticket_no_ignores_session_cache_with_other_user():
    chat_tools._CACHE = CacheClient(None)
    session_id = "sess-last-ticket-owner-1"
    chat_tools._CACHE.set_json(
        chat_tools._last_ticket_cache_key(session_id),
        {"ticket_no": "STK202602239001", "user_id": "other-user"},
        ttl=300,
    )
    chat_tools._CACHE.set_json(
        chat_tools._last_ticket_user_cache_key("owner-user"),
        {"ticket_no": "STK202602239002"},
        ttl=300,
    )

    metric_key = "chat_ticket_session_cache_owner_mismatch_total{cache=last_ticket}"
    before_metrics = dict(chat_tools.metrics.snapshot())
    loaded = chat_tools._load_last_ticket_no(session_id, "owner-user")
    after_metrics = chat_tools.metrics.snapshot()
    assert loaded == "STK202602239002"
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1


def test_load_ticket_create_last_ignores_session_cache_with_other_user():
    chat_tools._CACHE = CacheClient(None)
    session_id = "sess-cooldown-owner-1"
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_last_cache_key(session_id),
        {"created_at": 1_700_200_100, "user_id": "other-user"},
        ttl=300,
    )
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_last_user_cache_key("owner-user"),
        {"created_at": 1_700_200_200},
        ttl=300,
    )

    metric_key = "chat_ticket_session_cache_owner_mismatch_total{cache=create_last}"
    before_metrics = dict(chat_tools.metrics.snapshot())
    loaded = chat_tools._load_ticket_create_last(session_id, "owner-user")
    after_metrics = chat_tools.metrics.snapshot()
    assert loaded == 1_700_200_200
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1


def test_reset_ticket_session_context_clears_session_ticket_state(monkeypatch):
    chat_tools._CACHE = CacheClient(None)
    session_id = "sess-ticket-reset-1"
    user_id = "ticket-reset-user-1"
    query = "문의 접수해줘 결제 오류가 반복되고 있어요"
    fingerprint = chat_tools._ticket_create_fingerprint(user_id, query)

    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_cache_key(session_id, fingerprint),
        {
            "ticket_no": "STK202602230401",
            "status": "RECEIVED",
            "expected_response_minutes": 200,
            "cached_at": 111,
        },
        ttl=300,
    )
    chat_tools._CACHE.set_json(chat_tools._last_ticket_cache_key(session_id), {"ticket_no": "STK202602230401"}, ttl=300)
    chat_tools._CACHE.set_json(chat_tools._ticket_create_last_cache_key(session_id), {"created_at": 1_700_200_000}, ttl=300)

    before_epoch = chat_tools._ticket_create_dedup_epoch(session_id)
    chat_tools.reset_ticket_session_context(session_id)
    after_epoch = chat_tools._ticket_create_dedup_epoch(session_id)
    dedup_cached, dedup_scope = chat_tools._load_ticket_create_dedup(session_id, user_id, fingerprint)

    assert after_epoch == before_epoch + 1
    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_cache_key(session_id)) == {"cleared": True}
    assert chat_tools._CACHE.get_json(chat_tools._ticket_create_last_cache_key(session_id)) == {"cleared": True}
    assert dedup_cached is None
    assert dedup_scope is None


def test_reset_ticket_session_context_clears_user_ticket_state_from_session_pattern():
    chat_tools._CACHE = CacheClient(None)
    session_id = "u:777:default"
    user_id = "777"
    query = "문의 접수해줘 결제 오류가 반복되고 있어요"
    fingerprint = chat_tools._ticket_create_fingerprint(user_id, query)
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_user_cache_key(user_id, fingerprint),
        {
            "ticket_no": "STK202602230777",
            "status": "RECEIVED",
            "expected_response_minutes": 180,
            "cached_at": 222,
        },
        ttl=300,
    )
    chat_tools._CACHE.set_json(chat_tools._last_ticket_user_cache_key(user_id), {"ticket_no": "STK202602230402"}, ttl=300)
    chat_tools._CACHE.set_json(chat_tools._ticket_create_last_user_cache_key(user_id), {"created_at": 1_700_200_010}, ttl=300)

    metric_key = "chat_ticket_context_reset_total{reason=session_reset}"
    scope_metric_key = "chat_ticket_context_reset_scope_total{scope=session_and_user}"
    before_user_epoch = chat_tools._ticket_create_dedup_user_epoch(user_id)
    before_metrics = dict(chat_tools.metrics.snapshot())
    chat_tools.reset_ticket_session_context(session_id)
    after_metrics = chat_tools.metrics.snapshot()
    after_user_epoch = chat_tools._ticket_create_dedup_user_epoch(user_id)
    dedup_cached, dedup_scope = chat_tools._load_ticket_create_dedup(session_id, user_id, fingerprint)

    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_user_cache_key(user_id)) == {"cleared": True}
    assert chat_tools._CACHE.get_json(chat_tools._ticket_create_last_user_cache_key(user_id)) == {"cleared": True}
    assert after_user_epoch == before_user_epoch + 1
    assert dedup_cached is None
    assert dedup_scope is None
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1
    assert after_metrics.get(scope_metric_key, 0) >= before_metrics.get(scope_metric_key, 0) + 1


def test_reset_ticket_session_context_clears_user_ticket_state_for_short_user_session_pattern():
    chat_tools._CACHE = CacheClient(None)
    session_id = "u:778"
    user_id = "778"
    chat_tools._CACHE.set_json(chat_tools._last_ticket_user_cache_key(user_id), {"ticket_no": "STK202602230778"}, ttl=300)
    chat_tools._CACHE.set_json(chat_tools._ticket_create_last_user_cache_key(user_id), {"created_at": 1_700_200_020}, ttl=300)

    chat_tools.reset_ticket_session_context(session_id)

    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_user_cache_key(user_id)) == {"cleared": True}
    assert chat_tools._CACHE.get_json(chat_tools._ticket_create_last_user_cache_key(user_id)) == {"cleared": True}


def test_reset_ticket_session_context_records_session_only_scope_metric():
    chat_tools._CACHE = CacheClient(None)
    session_id = "sess-ticket-reset-no-user"
    user_id = "999"
    chat_tools._CACHE.set_json(chat_tools._last_ticket_user_cache_key(user_id), {"ticket_no": "STK202602239999"}, ttl=300)
    chat_tools._CACHE.set_json(chat_tools._ticket_create_last_user_cache_key(user_id), {"created_at": 1_700_200_099}, ttl=300)
    scope_metric_key = "chat_ticket_context_reset_scope_total{scope=session_only}"
    before_metrics = dict(chat_tools.metrics.snapshot())

    chat_tools.reset_ticket_session_context(session_id)
    after_metrics = chat_tools.metrics.snapshot()

    assert after_metrics.get(scope_metric_key, 0) >= before_metrics.get(scope_metric_key, 0) + 1
    assert chat_tools._CACHE.get_json(chat_tools._last_ticket_user_cache_key(user_id)) == {"ticket_no": "STK202602239999"}
    assert chat_tools._CACHE.get_json(chat_tools._ticket_create_last_user_cache_key(user_id)) == {"created_at": 1_700_200_099}


def test_run_tool_chat_ticket_status_lookup_uses_user_recent_ticket_across_sessions(monkeypatch):
    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            return {
                "ticket": {
                    "ticket_id": 31,
                    "ticket_no": "STK202602230301",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 120,
            }
        if method == "GET" and path == "/support/tickets/by-number/STK202602230301":
            return {
                "ticket": {
                    "ticket_id": 31,
                    "ticket_no": "STK202602230301",
                    "status": "IN_PROGRESS",
                    "severity": "LOW",
                },
                "expected_response_minutes": 120,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    user_id = "ticket-status-cross-user-1"

    create_result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-cross-1",
                "message": {"role": "user", "content": "문의 접수해줘 결제 오류가 반복되고 있어요"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_create_cross",
        )
    )
    assert create_result is not None
    assert create_result["status"] == "ok"
    assert "STK202602230301" in create_result["answer"]["content"]

    status_result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-status-cross-2",
                "message": {"role": "user", "content": "내 문의 상태 알려줘"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_status_cross",
        )
    )

    assert status_result is not None
    assert status_result["status"] == "ok"
    assert "STK202602230301" in status_result["answer"]["content"]
    assert "처리 중" in status_result["answer"]["content"]


def test_run_tool_chat_ticket_create_ignores_other_user_session_cooldown(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 32,
                    "ticket_no": "STK202602230302",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 100,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    monkeypatch.setattr(chat_tools, "_ticket_create_cooldown_sec", lambda: 60)
    monkeypatch.setattr(chat_tools.time, "time", lambda: 1_700_300_000)

    session_id = "sess-shared-legacy"
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_last_cache_key(session_id),
        {"created_at": 1_700_299_980, "user_id": "other-user"},
        ttl=300,
    )

    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "문의 접수해줘 결제 오류가 반복돼요"},
                "client": {"locale": "ko-KR", "user_id": "owner-user"},
            },
            "trace_test",
            "req_ticket_owner",
        )
    )

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230302" in result["answer"]["content"]
    assert call_count["ticket_create"] == 1


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


def test_run_tool_chat_ticket_create_uses_history_issue_context(monkeypatch):
    captured = {}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "GET" and path == "/orders/12":
            return {
                "order": {
                    "order_id": 12,
                    "order_no": "ORD202602220012",
                    "status": "PAID",
                    "total_amount": 33000,
                    "shipping_fee": 3000,
                    "payment_method": "CARD",
                }
            }
        if method == "POST" and path == "/support/tickets":
            captured["payload"] = kwargs.get("payload")
            return {
                "ticket": {
                    "ticket_id": 61,
                    "ticket_no": "STK202602230610",
                    "status": "RECEIVED",
                    "severity": "MEDIUM",
                },
                "expected_response_minutes": 130,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-history-ctx-1",
                "message": {"role": "user", "content": "문의 접수해줘"},
                "history": [
                    {"role": "user", "content": "주문 12 환불이 진행되지 않고 결제 내역도 다릅니다."},
                    {"role": "assistant", "content": "확인을 도와드릴게요."},
                ],
                "client": {"locale": "ko-KR", "user_id": "1"},
            },
            "trace_test",
            "req_ticket_history_ctx",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230610" in result["answer"]["content"]
    assert captured["payload"]["summary"] == "주문 12 환불이 진행되지 않고 결제 내역도 다릅니다."
    assert captured["payload"]["details"]["effectiveQuery"] == "주문 12 환불이 진행되지 않고 결제 내역도 다릅니다."
    assert after_metrics.get("chat_ticket_create_with_context_total{source=history}", 0) >= before_metrics.get(
        "chat_ticket_create_with_context_total{source=history}",
        0,
    ) + 1


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

    metric_miss_key = "chat_ticket_create_dedup_lookup_total{result=miss}"
    metric_session_key = "chat_ticket_create_dedup_lookup_total{result=session}"
    before_metrics = dict(chat_tools.metrics.snapshot())
    first = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_1"))
    second = asyncio.run(chat_tools.run_tool_chat(payload, "trace_test", "req_create_2"))
    after_metrics = chat_tools.metrics.snapshot()

    assert first is not None and first["status"] == "ok"
    assert second is not None and second["status"] == "ok"
    assert "STK202602230201" in second["answer"]["content"]
    assert "재사용" in second["answer"]["content"]
    assert call_count["ticket_create"] == 1
    assert after_metrics.get(metric_miss_key, 0) >= before_metrics.get(metric_miss_key, 0) + 1
    assert after_metrics.get(metric_session_key, 0) >= before_metrics.get(metric_session_key, 0) + 1


def test_run_tool_chat_ticket_create_is_idempotent_across_sessions_same_user(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 25,
                    "ticket_no": "STK202602230205",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 140,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    user_id = "dedup-cross-user-1"

    first = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-dedup-cross-1",
                "message": {"role": "user", "content": "문의 접수해줘 결제 확인 문자가 중복 발송돼요"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_create_cross_1",
        )
    )
    before_metrics = dict(chat_tools.metrics.snapshot())
    second = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-dedup-cross-2",
                "message": {"role": "user", "content": "문의 접수해줘 결제 확인 문자가 중복 발송돼요"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_create_cross_2",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert first is not None and first["status"] == "ok"
    assert second is not None and second["status"] == "ok"
    assert "STK202602230205" in second["answer"]["content"]
    assert "재사용" in second["answer"]["content"]
    assert call_count["ticket_create"] == 1
    metric_key = "chat_ticket_create_dedup_scope_total{scope=user}"
    lookup_metric_key = "chat_ticket_create_dedup_lookup_total{result=user}"
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1
    assert after_metrics.get(lookup_metric_key, 0) >= before_metrics.get(lookup_metric_key, 0) + 1


def test_run_tool_chat_ticket_create_dedup_prefers_latest_cache_entry():
    session_id = "sess-ticket-dedup-latest-1"
    user_id = "dedup-latest-user-1"
    query = "문의 접수해줘 결제 확인 문자가 중복 발송돼요"
    fingerprint = chat_tools._ticket_create_fingerprint(user_id, query)

    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_cache_key(session_id, fingerprint),
        {
            "ticket_no": "STK202602230210",
            "status": "RECEIVED",
            "expected_response_minutes": 180,
            "cached_at": 100,
        },
        ttl=300,
    )
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_user_cache_key(user_id, fingerprint),
        {
            "ticket_no": "STK202602230211",
            "status": "IN_PROGRESS",
            "expected_response_minutes": 120,
            "cached_at": 200,
        },
        ttl=300,
    )

    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": query},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_dedup_latest",
        )
    )

    assert result is not None
    assert result["status"] == "ok"
    assert "STK202602230211" in result["answer"]["content"]
    assert "처리 중" in result["answer"]["content"]


def test_load_ticket_create_dedup_prefers_session_scope_on_equal_cached_at():
    session_id = "sess-ticket-dedup-tie-1"
    user_id = "dedup-tie-user-1"
    query = "문의 접수해줘 결제 확인 문자가 중복 발송돼요"
    fingerprint = chat_tools._ticket_create_fingerprint(user_id, query)
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_cache_key(session_id, fingerprint),
        {
            "ticket_no": "STK202602230212",
            "status": "RECEIVED",
            "expected_response_minutes": 180,
            "cached_at": 300,
        },
        ttl=300,
    )
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_dedup_user_cache_key(user_id, fingerprint),
        {
            "ticket_no": "STK202602230213",
            "status": "IN_PROGRESS",
            "expected_response_minutes": 120,
            "cached_at": 300,
        },
        ttl=300,
    )

    dedup_cached, dedup_scope = chat_tools._load_ticket_create_dedup(session_id, user_id, fingerprint)

    assert dedup_scope == "session"
    assert dedup_cached is not None
    assert dedup_cached.get("ticket_no") == "STK202602230212"


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
        "client": {"locale": "ko-KR", "user_id": "cooldown-user-1"},
    }
    second_payload = {
        "session_id": session_id,
        "message": {"role": "user", "content": "문의 접수해줘 배송지가 잘못 입력됐어요"},
        "client": {"locale": "ko-KR", "user_id": "cooldown-user-1"},
    }

    metric_key = "chat_ticket_create_rate_limited_total{result=blocked}"
    before_metrics = dict(chat_tools.metrics.snapshot())
    first = asyncio.run(chat_tools.run_tool_chat(first_payload, "trace_test", "req_create_1"))
    second = asyncio.run(chat_tools.run_tool_chat(second_payload, "trace_test", "req_create_2"))
    after_metrics = chat_tools.metrics.snapshot()

    assert first is not None and first["status"] == "ok"
    assert second is not None
    assert second["status"] == "needs_input"
    assert second["reason_code"] == "RATE_LIMITED"
    assert second["next_action"] == "RETRY"
    assert second["recoverable"] is True
    assert int(second["retry_after_ms"] or 0) > 0
    assert "다시 시도" in second["answer"]["content"]
    assert "STK202602230203" in second["answer"]["content"]
    assert second["citations"]
    assert second["sources"][0]["url"] == "POST /api/v1/support/tickets"
    assert call_count["ticket_create"] == 1
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1
    context_metric_key = "chat_ticket_create_rate_limited_context_total{has_recent_ticket=true}"
    assert after_metrics.get(context_metric_key, 0) >= before_metrics.get(context_metric_key, 0) + 1


def test_run_tool_chat_ticket_create_applies_cooldown_without_recent_ticket_hint(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 33,
                    "ticket_no": "STK202602230303",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 80,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    monkeypatch.setattr(chat_tools, "_ticket_create_cooldown_sec", lambda: 60)
    monkeypatch.setattr(chat_tools.time, "time", lambda: 1_700_300_120)

    session_id = "sess-ticket-cooldown-no-recent-1"
    user_id = "cooldown-user-3"
    chat_tools._CACHE.set_json(
        chat_tools._ticket_create_last_cache_key(session_id),
        {"created_at": 1_700_300_100, "user_id": user_id},
        ttl=120,
    )

    metric_key = "chat_ticket_create_rate_limited_context_total{has_recent_ticket=false}"
    before_metrics = dict(chat_tools.metrics.snapshot())
    result = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "문의 접수해줘 배송 상태가 계속 갱신되지 않아요"},
                "client": {"locale": "ko-KR", "user_id": user_id},
            },
            "trace_test",
            "req_cooldown_no_recent",
        )
    )
    after_metrics = chat_tools.metrics.snapshot()

    assert result is not None
    assert result["status"] == "needs_input"
    assert result["reason_code"] == "RATE_LIMITED"
    assert "기존 접수번호" not in result["answer"]["content"]
    assert call_count["ticket_create"] == 0
    assert after_metrics.get(metric_key, 0) >= before_metrics.get(metric_key, 0) + 1


def test_run_tool_chat_ticket_create_applies_cooldown_across_sessions_same_user(monkeypatch):
    call_count = {"ticket_create": 0}

    async def fake_call_commerce(method, path, **kwargs):
        if method == "POST" and path == "/support/tickets":
            call_count["ticket_create"] += 1
            return {
                "ticket": {
                    "ticket_id": 24,
                    "ticket_no": "STK202602230204",
                    "status": "RECEIVED",
                    "severity": "LOW",
                },
                "expected_response_minutes": 150,
            }
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(chat_tools, "_call_commerce", fake_call_commerce)
    monkeypatch.setattr(chat_tools, "_ticket_create_cooldown_sec", lambda: 45)
    monkeypatch.setattr(chat_tools.time, "time", lambda: 1_700_000_100)

    first = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-cooldown-user-1",
                "message": {"role": "user", "content": "문의 접수해줘 결제 내역이 중복 청구됐어요"},
                "client": {"locale": "ko-KR", "user_id": "cooldown-user-2"},
            },
            "trace_test",
            "req_create_user_1",
        )
    )
    second = asyncio.run(
        chat_tools.run_tool_chat(
            {
                "session_id": "sess-ticket-cooldown-user-2",
                "message": {"role": "user", "content": "문의 접수해줘 배송 예정일이 계속 밀려요"},
                "client": {"locale": "ko-KR", "user_id": "cooldown-user-2"},
            },
            "trace_test",
            "req_create_user_2",
        )
    )

    assert first is not None and first["status"] == "ok"
    assert second is not None
    assert second["status"] == "needs_input"
    assert second["reason_code"] == "RATE_LIMITED"
    assert second["next_action"] == "RETRY"
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


def test_build_response_repairs_success_claim_without_evidence():
    response = chat_tools._build_response(
        "trace_test",
        "req_claim_no_evidence",
        "ok",
        "주문 조회가 완료되었습니다.",
    )

    assert response["status"] == "tool_fallback"
    assert response["reason_code"] == "DENY_CLAIM:NO_TOOL_RESULT"
    assert response["next_action"] == "RETRY"


def test_build_response_repairs_not_confirmed_success_claim():
    response = chat_tools._build_response(
        "trace_test",
        "req_claim_not_confirmed",
        "pending_confirmation",
        "환불 접수가 완료되었습니다.",
    )

    assert response["status"] == "pending_confirmation"
    assert response["reason_code"] == "DENY_CLAIM:NOT_CONFIRMED"
    assert response["next_action"] == "CONFIRM_ACTION"
    assert "확인 절차" in response["answer"]["content"]


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


def test_call_commerce_timeout_appends_failure_audit(monkeypatch):
    audit_calls = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, timeout=None):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(chat_tools.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(chat_tools, "_tool_lookup_retry_count", lambda: 0)
    monkeypatch.setattr(chat_tools, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

    with pytest.raises(chat_tools.ToolCallError):
        asyncio.run(
            chat_tools._call_commerce(
                "GET",
                "/orders/12",
                user_id="1",
                trace_id="trace_test",
                request_id="req_timeout_audit",
                tool_name="order_lookup",
                intent="ORDER_LOOKUP",
            )
        )

    assert any(call.get("result") == "FAIL" and call.get("reason_code") == "TOOL_TIMEOUT" for call in audit_calls)


def test_call_commerce_includes_tenant_header_and_appends_audit(monkeypatch):
    captured_headers = {}
    audit_calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"ok": True}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, timeout=None):
            captured_headers.update(headers or {})
            return FakeResponse()

    monkeypatch.setenv("BSL_TENANT_ID", "books-test")
    monkeypatch.setattr(chat_tools.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(chat_tools, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

    result = asyncio.run(
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

    assert result["ok"] is True
    assert captured_headers["x-user-id"] == "1"
    assert captured_headers["x-tenant-id"] == "books-test"
    assert len(audit_calls) == 1
    assert audit_calls[0]["decision"] == "ALLOW"
    assert audit_calls[0]["result"] == "SUCCESS"


def test_call_commerce_blocks_when_circuit_open_with_audit(monkeypatch):
    audit_calls = []
    chat_tools._CACHE.set_json(chat_tools._tool_circuit_open_key("order_lookup"), {"opened_until": int(chat_tools.time.time()) + 30}, ttl=30)
    monkeypatch.setattr(chat_tools, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

    with pytest.raises(chat_tools.ToolCallError) as exc_info:
        asyncio.run(
            chat_tools._call_commerce(
                "GET",
                "/orders/12",
                user_id="1",
                trace_id="trace_test",
                request_id="req_circuit_audit",
                tool_name="order_lookup",
                intent="ORDER_LOOKUP",
            )
        )

    assert exc_info.value.code == "tool_circuit_open"
    assert any(call.get("result") == "BLOCKED" and call.get("reason_code") == "TOOL_CIRCUIT_OPEN" for call in audit_calls)


def test_call_commerce_blocks_when_auth_context_missing(monkeypatch):
    with pytest.raises(chat_tools.ToolCallError) as exc_info:
        asyncio.run(
            chat_tools._call_commerce(
                "GET",
                "/orders/12",
                user_id="",
                trace_id="trace_test",
                request_id="req_test",
                tool_name="order_lookup",
                intent="ORDER_LOOKUP",
            )
        )

    assert exc_info.value.code == "auth_context_missing"


def test_call_commerce_records_failure_audit_on_http_500(monkeypatch):
    audit_calls = []

    class FakeResponse:
        status_code = 500
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"error": {"code": "server_error", "message": "boom"}}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr(chat_tools.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(chat_tools, "_tool_lookup_retry_count", lambda: 0)
    monkeypatch.setattr(chat_tools, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

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

    assert exc_info.value.code == "server_error"
    assert any(call.get("result") == "FAIL" and call.get("reason_code") == "TOOL_FAIL:SERVER_ERROR" for call in audit_calls)


def test_call_commerce_opens_circuit_after_timeout(monkeypatch):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, timeout=None):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(chat_tools.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(chat_tools, "_tool_lookup_retry_count", lambda: 0)
    monkeypatch.setattr(chat_tools, "_tool_circuit_fail_threshold", lambda: 1)
    monkeypatch.setattr(chat_tools, "_tool_circuit_open_sec", lambda: 60)

    with pytest.raises(chat_tools.ToolCallError):
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

    opened = chat_tools._CACHE.get_json(chat_tools._tool_circuit_open_key("order_lookup"))
    assert isinstance(opened, dict)
    assert int(opened.get("opened_until") or 0) > int(chat_tools.time.time())


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
