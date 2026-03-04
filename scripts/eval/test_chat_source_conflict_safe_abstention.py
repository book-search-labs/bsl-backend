import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_source_conflict_safe_abstention.py"
    spec = importlib.util.spec_from_file_location("chat_source_conflict_safe_abstention", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_safe_abstention_tracks_message_compliance():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "conflict_severity": "HIGH",
            "decision": "ABSTAIN",
            "response_text": "정보가 상충되어 확인이 필요합니다. 공식 안내: https://example.com/policy",
            "source_links": ["https://example.com/policy"],
            "reason_code": "CONFLICT_HIGH",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "conflict_severity": "HIGH",
            "decision": "ANSWER",
            "definitive_claim": True,
            "response_text": "환불 가능합니다.",
            "source_links": [],
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "conflict_severity": "LOW",
            "decision": "ANSWER",
            "response_text": "일반 안내입니다.",
        },
    ]
    summary = module.summarize_safe_abstention(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["high_conflict_total"] == 2
    assert summary["should_abstain_total"] == 2
    assert summary["abstain_total"] == 1
    assert summary["abstain_compliance_ratio"] == 0.5
    assert summary["unsafe_definitive_total"] == 1
    assert summary["missing_standard_phrase_total"] == 1
    assert summary["missing_source_link_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["message_quality_ratio"] == 0.5
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_safe_abstention_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "unsafe_definitive_total": 2,
            "abstain_compliance_ratio": 0.3,
            "missing_standard_phrase_total": 2,
            "missing_source_link_total": 2,
            "missing_reason_code_total": 2,
            "message_quality_ratio": 0.4,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_unsafe_definitive_total=0,
        min_abstain_compliance_ratio=0.9,
        max_missing_standard_phrase_total=0,
        max_missing_source_link_total=0,
        max_missing_reason_code_total=0,
        min_message_quality_ratio=0.9,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "unsafe_definitive_total": 0,
            "abstain_compliance_ratio": 1.0,
            "missing_standard_phrase_total": 0,
            "missing_source_link_total": 0,
            "missing_reason_code_total": 0,
            "message_quality_ratio": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_unsafe_definitive_total=1000000,
        min_abstain_compliance_ratio=0.0,
        max_missing_standard_phrase_total=1000000,
        max_missing_source_link_total=1000000,
        max_missing_reason_code_total=1000000,
        min_message_quality_ratio=0.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_source_conflict_abstention_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "should_abstain_total": 20,
            "abstain_total": 20,
            "unsafe_definitive_total": 0,
            "abstain_compliance_ratio": 1.0,
            "missing_standard_phrase_total": 0,
            "missing_source_link_total": 0,
            "missing_reason_code_total": 0,
            "message_quality_ratio": 1.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "should_abstain_total": 1,
            "abstain_total": 1,
            "unsafe_definitive_total": 1,
            "abstain_compliance_ratio": 0.2,
            "missing_standard_phrase_total": 1,
            "missing_source_link_total": 1,
            "missing_reason_code_total": 1,
            "message_quality_ratio": 0.3,
            "stale_minutes": 80.0,
        },
        max_should_abstain_total_drop=1,
        max_abstain_total_drop=1,
        max_unsafe_definitive_total_increase=0,
        max_abstain_compliance_ratio_drop=0.05,
        max_missing_standard_phrase_total_increase=0,
        max_missing_source_link_total_increase=0,
        max_missing_reason_code_total_increase=0,
        max_message_quality_ratio_drop=0.05,
        max_stale_minutes_increase=30.0,
    )
    assert any("should_abstain_total regression" in item for item in failures)
    assert any("abstain_total regression" in item for item in failures)
    assert any("unsafe_definitive_total regression" in item for item in failures)
    assert any("abstain_compliance_ratio regression" in item for item in failures)
    assert any("missing_standard_phrase_total regression" in item for item in failures)
    assert any("missing_source_link_total regression" in item for item in failures)
    assert any("missing_reason_code_total regression" in item for item in failures)
    assert any("message_quality_ratio regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
