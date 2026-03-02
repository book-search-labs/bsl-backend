from app.core.cache import CacheClient
from app.core.chat_graph import reason_taxonomy


def test_assess_reason_code_forbidden_code_is_invalid():
    assessment = reason_taxonomy.assess_reason_code("UNKNOWN", source="response")

    assert assessment.invalid is True
    assert assessment.valid is False
    assert assessment.normalized_reason_code == "CHAT_REASON_CODE_INVALID"


def test_assess_reason_code_source_policy_violation_is_unknown():
    assessment = reason_taxonomy.assess_reason_code("PROVIDER_TIMEOUT", source="policy_decide")

    assert assessment.invalid is False
    assert assessment.unknown is True
    assert assessment.source_policy_violation is True


def test_record_reason_code_event_and_summary():
    reason_taxonomy._CACHE = CacheClient(None)

    reason_taxonomy.record_reason_code_event(
        session_id="u:701:default",
        trace_id="trace_701",
        request_id="req_701",
        source="response",
        reason_code="OK",
    )
    reason_taxonomy.record_reason_code_event(
        session_id="u:701:default",
        trace_id="trace_701",
        request_id="req_702",
        source="response",
        reason_code="UNKNOWN",
    )

    summary = reason_taxonomy.build_reason_code_summary(limit=10)
    assert summary["window_size"] == 2
    assert summary["invalid_total"] == 1
    assert summary["unknown_total"] == 0
    assert summary["by_reason_code"]["OK"] == 1
    assert summary["by_reason_code"]["CHAT_REASON_CODE_INVALID"] == 1

    rows = reason_taxonomy.load_reason_code_audit("u:701:default")
    assert len(rows) == 2
    assert rows[-1]["invalid"] is True
