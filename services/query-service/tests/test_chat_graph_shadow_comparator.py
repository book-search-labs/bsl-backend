from app.core.cache import CacheClient
from app.core.chat_graph import shadow_comparator


def _base_response(status: str = "ok", reason_code: str = "OK", next_action: str = "NONE", recoverable: bool = False, citations=None):
    if citations is None:
        citations = ["c1"]
    return {
        "version": "v1",
        "trace_id": "trace",
        "request_id": "req",
        "status": status,
        "reason_code": reason_code,
        "recoverable": recoverable,
        "next_action": next_action,
        "retry_after_ms": None,
        "answer": {"role": "assistant", "content": "ok"},
        "sources": [],
        "citations": citations,
    }


def test_compare_shadow_response_matches_when_critical_fields_equal():
    legacy = _base_response()
    graph = _base_response()

    result = shadow_comparator.compare_shadow_response(legacy, graph)

    assert result.matched is True
    assert result.diff_types == []
    assert result.severity == "INFO"


def test_compare_shadow_response_marks_action_diff_as_blocker():
    legacy = _base_response(next_action="NONE", recoverable=False)
    graph = _base_response(next_action="OPEN_SUPPORT_TICKET", recoverable=True)

    result = shadow_comparator.compare_shadow_response(legacy, graph)

    assert result.matched is False
    assert "ACTION_DIFF" in result.diff_types
    assert result.severity == "BLOCKER"


def test_shadow_summary_and_gate_payload():
    shadow_comparator._CACHE = CacheClient(None)

    matched = shadow_comparator.compare_shadow_response(_base_response(), _base_response())
    mismatch = shadow_comparator.compare_shadow_response(_base_response(), _base_response(reason_code="PROVIDER_TIMEOUT"))

    shadow_comparator.append_shadow_diff(
        session_id="u:101:default",
        trace_id="trace_1",
        request_id="req_1",
        intent="ORDER",
        topic="주문 상태",
        result=matched,
    )
    shadow_comparator.append_shadow_diff(
        session_id="u:101:default",
        trace_id="trace_2",
        request_id="req_2",
        intent="ORDER",
        topic="주문 상태",
        result=mismatch,
    )

    summary = shadow_comparator.build_shadow_summary(limit=10)
    gate = shadow_comparator.build_gate_payload(limit=10)

    assert summary["window_size"] == 2
    assert summary["mismatched"] == 1
    assert gate["gate_status"] in {"PASS", "WARN", "BLOCK"}
    assert isinstance(summary["by_type"], dict)
