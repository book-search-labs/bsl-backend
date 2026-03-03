import asyncio

from app.core.cache import CacheClient
from app.core.chat_graph import authz_gate, confirm_fsm, domain_nodes, langsmith_trace, launch_metrics, perf_budget
from app.core.chat_graph.runtime import run_chat_graph


def _run(coro):
    return asyncio.run(coro)


def test_run_chat_graph_happy_path_returns_legacy_response_shape():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:101:default", "message": {"role": "user", "content": "배송 상태 알려줘"}},
            "trace_1",
            "req_1",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.stage == "persist"
    assert result.response["status"] == "ok"
    assert result.response["reason_code"] == "OK"
    assert result.state["route"] == "ANSWER"
    assert result.state["state_version"] == 2


def test_run_chat_graph_routes_empty_query_to_ask_without_executor_call():
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:102:default", "message": {"role": "user", "content": ""}},
            "trace_2",
            "req_2",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "NO_MESSAGES"
    assert result.response["next_action"] == "PROVIDE_REQUIRED_INFO"
    assert "다시 입력" in str(result.response["answer"]["content"])


def test_run_chat_graph_fallbacks_when_legacy_response_is_not_object():
    async def fake_legacy_executor(request, trace_id, request_id):
        return "invalid"  # type: ignore[return-value]

    result = _run(
        run_chat_graph(
            {"session_id": "u:103:default", "message": {"role": "user", "content": "주문 상태"}},
            "trace_3",
            "req_3",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "CHAT_GRAPH_EXECUTION_ERROR"
    assert result.state["tool_result"]["source"] == "legacy_executor"


def test_run_chat_graph_maps_timeout_to_korean_retry_template():
    async def fake_legacy_executor(request, trace_id, request_id):
        raise TimeoutError("timeout")

    result = _run(
        run_chat_graph(
            {"session_id": "u:103b:default", "message": {"role": "user", "content": "주문 상태"}},
            "trace_3b",
            "req_3b",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "PROVIDER_TIMEOUT"
    assert result.response["next_action"] == "RETRY"
    assert "응답 시간이 지연" in str(result.response["answer"]["content"])


def test_run_chat_graph_sanitizes_forbidden_reason_code():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "insufficient_evidence",
            "reason_code": "UNKNOWN",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 1000,
            "answer": {"role": "assistant", "content": "재시도해 주세요."},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:104:default", "message": {"role": "user", "content": "상태 알려줘"}},
            "trace_104",
            "req_104",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["reason_code"] == "CHAT_REASON_CODE_INVALID"
    assert result.state["reason_code"] == "CHAT_REASON_CODE_INVALID"


def test_run_chat_graph_emits_langsmith_audit_events_even_when_disabled(monkeypatch):
    langsmith_trace._CACHE = CacheClient(None)
    monkeypatch.delenv("QS_CHAT_LANGSMITH_ENABLED", raising=False)

    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    _run(
        run_chat_graph(
            {"session_id": "u:105:default", "message": {"role": "user", "content": "배송 상태 알려줘"}},
            "trace_105",
            "req_105",
            legacy_executor=fake_legacy_executor,
        )
    )

    rows = langsmith_trace.load_trace_audit("u:105:default")
    assert len(rows) >= 3
    assert rows[0]["event_type"] == "run_start"
    assert rows[-1]["event_type"] in {"run_end", "run_error"}


def test_run_chat_graph_routes_selection_reference_to_options():
    domain_nodes._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {"status": "ok", "reason_code": "OK", "answer": {"role": "assistant", "content": "응답"}, "sources": [], "citations": []}

    result = _run(
        run_chat_graph(
            {"session_id": "u:106:default", "message": {"role": "user", "content": "그거 자세히 알려줘"}},
            "trace_106",
            "req_106",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["reason_code"] == "ROUTE_OPTIONS_SELECTION_REQUIRED"
    assert result.response["status"] == "insufficient_evidence"


def test_run_chat_graph_policy_topic_cache_hit_skips_executor(monkeypatch):
    domain_nodes._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "환불 정책 안내"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    request = {"session_id": "u:107:default", "message": {"role": "user", "content": "환불 정책 안내해줘"}}
    _run(run_chat_graph(request, "trace_107a", "req_107a", legacy_executor=fake_legacy_executor))
    second = _run(run_chat_graph(request, "trace_107b", "req_107b", legacy_executor=fake_legacy_executor))

    assert called["count"] == 1
    assert second.response["status"] == "ok"
    assert second.state["tool_result"]["source"] == "policy_topic_cache"


def test_run_chat_graph_selection_memory_rewrites_second_turn_query():
    domain_nodes._CACHE = CacheClient(None)
    captured_queries: list[str] = []

    async def fake_legacy_executor(request, trace_id, request_id):
        message = request.get("message") if isinstance(request.get("message"), dict) else {}
        captured_queries.append(str(message.get("content") or ""))
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "추천 결과"},
            "sources": [
                {"title": "A Book", "doc_id": "a1"},
                {"title": "B Book", "doc_id": "b1"},
            ],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    first = {"session_id": "u:108:default", "message": {"role": "user", "content": "책 추천해줘"}}
    second = {"session_id": "u:108:default", "message": {"role": "user", "content": "2번째 자세히 알려줘"}}

    _run(run_chat_graph(first, "trace_108a", "req_108a", legacy_executor=fake_legacy_executor))
    _run(run_chat_graph(second, "trace_108b", "req_108b", legacy_executor=fake_legacy_executor))

    assert len(captured_queries) == 2
    assert captured_queries[1].startswith("B Book")


def test_run_chat_graph_claim_verifier_blocks_unbacked_success_claim():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "주문 취소 완료했습니다."},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:109:default", "message": {"role": "user", "content": "안내해줘"}},
            "trace_109",
            "req_109",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "OUTPUT_GUARD_FORBIDDEN_CLAIM"


def test_run_chat_graph_claim_verifier_allows_success_claim_with_citations():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "주문 상태 조회 완료했습니다."},
            "sources": [{"doc_id": "order-policy", "title": "주문 정책", "snippet": "조회 정책"}],
            "citations": ["order-policy#0"],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:109b:default", "message": {"role": "user", "content": "주문 상태 알려줘"}},
            "trace_109b",
            "req_109b",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["status"] == "ok"
    assert result.response["reason_code"] == "OK"


def test_run_chat_graph_compose_sets_ui_hints_for_confirm():
    confirm_fsm._CACHE = CacheClient(None)
    authz_gate._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "unused"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    request = {
        "session_id": "u:110c:default",
        "message": {"role": "user", "content": "환불 요청 진행해줘"},
        "client": {
            "user_id": "110c",
            "tenant_id": "default",
            "auth_context": {"scopes": ["chat:write"], "assurance_level": "high"},
        },
    }
    result = _run(run_chat_graph(request, "trace_110c", "req_110c", legacy_executor=fake_legacy_executor))

    assert called["count"] == 0
    assert result.state["route"] == "CONFIRM"
    assert result.response["reason_code"] == "CONFIRMATION_REQUIRED"
    tool_result = result.state.get("tool_result")
    assert isinstance(tool_result, dict)
    data = tool_result.get("data")
    assert isinstance(data, dict)
    ui_hints = data.get("ui_hints")
    assert isinstance(ui_hints, dict)
    buttons = ui_hints.get("buttons")
    assert isinstance(buttons, list)
    assert any(item.get("id") == "confirm" for item in buttons if isinstance(item, dict))
    assert any(item.get("id") == "abort" for item in buttons if isinstance(item, dict))


def test_run_chat_graph_compose_sets_ui_hints_for_options():
    domain_nodes._CACHE = CacheClient(None)
    domain_nodes.save_selection_memory(
        "u:110:default",
        {
            "last_candidates": [
                {"title": "A Book", "doc_id": "a1"},
                {"title": "B Book", "doc_id": "b1"},
            ],
            "selected_index": None,
            "selected_book": None,
        },
    )

    async def fake_legacy_executor(request, trace_id, request_id):
        return {"status": "ok", "reason_code": "OK", "answer": {"role": "assistant", "content": "unused"}, "sources": [], "citations": []}

    result = _run(
        run_chat_graph(
            {"session_id": "u:110:default", "message": {"role": "user", "content": "3번째 알려줘"}},
            "trace_110",
            "req_110",
            legacy_executor=fake_legacy_executor,
        )
    )

    tool_result = result.state.get("tool_result")
    assert isinstance(tool_result, dict)
    data = tool_result.get("data")
    assert isinstance(data, dict)
    ui_hints = data.get("ui_hints")
    assert isinstance(ui_hints, dict)
    assert len(ui_hints.get("options") or []) >= 1


def test_run_chat_graph_compose_sets_answer_cards_from_sources_when_selection_missing():
    domain_nodes._CACHE = CacheClient(None)

    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "추천 결과 안내"},
            "sources": [
                {"title": "정책 문서", "doc_id": "policy-1", "snippet": "요약"},
                {"title": "도서 메타", "doc_id": "book-1", "snippet": "메타"},
            ],
            "citations": ["policy-1#0"],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:110d:default", "message": {"role": "user", "content": "환불 정책 알려줘"}},
            "trace_110d",
            "req_110d",
            legacy_executor=fake_legacy_executor,
        )
    )

    tool_result = result.state.get("tool_result")
    assert isinstance(tool_result, dict)
    data = tool_result.get("data")
    assert isinstance(data, dict)
    ui_hints = data.get("ui_hints")
    assert isinstance(ui_hints, dict)
    cards = ui_hints.get("cards")
    assert isinstance(cards, list)
    assert any(card.get("title") == "정책 문서" for card in cards if isinstance(card, dict))


def test_run_chat_graph_records_perf_budget_sample():
    perf_budget._CACHE = CacheClient(None)

    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    _run(
        run_chat_graph(
            {"session_id": "u:111:default", "message": {"role": "user", "content": "안녕"}},
            "trace_111",
            "req_111",
            legacy_executor=fake_legacy_executor,
        )
    )

    summary = perf_budget.build_perf_summary(limit=10)
    assert summary["window_size"] >= 1


def test_run_chat_graph_records_launch_readiness_metrics():
    launch_metrics._CACHE = CacheClient(None)

    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    _run(
        run_chat_graph(
            {"session_id": "u:112:default", "message": {"role": "user", "content": "주문 상태 알려줘"}},
            "trace_112",
            "req_112",
            legacy_executor=fake_legacy_executor,
        )
    )

    summary = launch_metrics.load_launch_metrics_summary()
    assert summary["total"] >= 1
    assert isinstance(summary.get("by_intent"), dict)


def test_run_chat_graph_denies_sensitive_action_without_auth_context():
    confirm_fsm._CACHE = CacheClient(None)
    authz_gate._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {
                "session_id": "u:301:default",
                "message": {"role": "user", "content": "주문 취소해줘"},
                "client": {"user_id": "301"},
            },
            "trace_4",
            "req_4",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["reason_code"] == "AUTH_CONTEXT_MISSING"
    assert result.response["next_action"] == "OPEN_SUPPORT_TICKET"


def test_run_chat_graph_denies_cross_user_sensitive_action():
    confirm_fsm._CACHE = CacheClient(None)
    authz_gate._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {
                "session_id": "u:401:default",
                "message": {"role": "user", "content": "주문 취소해줘"},
                "client": {
                    "user_id": "401",
                    "tenant_id": "tenant-a",
                    "auth_context": {"scopes": ["chat:write"]},
                },
            },
            "trace_5",
            "req_5",
            legacy_executor=fake_legacy_executor,
        )
    )
    pending = confirm_fsm.load_pending_action("u:401:default")
    assert isinstance(pending, dict)
    protocol = pending.get("action_protocol")
    if isinstance(protocol, dict):
        protocol.setdefault("args", {})["target_user_id"] = "999"
        pending["action_protocol"] = protocol
        confirm_fsm.save_pending_action("u:401:default", pending)

    denied = _run(
        run_chat_graph(
            {
                "session_id": "u:401:default",
                "message": {"role": "user", "content": "확인 000000"},
                "client": {
                    "user_id": "401",
                    "tenant_id": "tenant-a",
                    "auth_context": {"scopes": ["chat:write"]},
                },
            },
            "trace_6",
            "req_6",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert denied.response["reason_code"] == "AUTH_FORBIDDEN"
