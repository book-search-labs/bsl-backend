import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_answer_band_policy_guard.py"
    spec = importlib.util.spec_from_file_location("chat_answer_band_policy_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_answer_band_policy_guard_tracks_policy_violations():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-04T00:00:00Z", "risk_band": "R1", "response_text": "안내드릴게요."},
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "risk_band": "R2",
            "response_text": "추가 확인이 필요합니다. 검토 후 안내드릴게요.",
            "approval_action": "REVIEW_QUEUE",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "risk_band": "R2",
            "response_text": "처리 완료되었습니다.",
            "approval_action": "AUTO_REPLY",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "risk_band": "R3",
            "response_text": "자동으로 처리할 수 없습니다. 상담사 연결을 도와드릴게요.",
            "approval_action": "HANDOFF",
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "risk_band": "R3",
            "response_text": "환불을 실행했습니다.",
            "approval_action": "AUTO_REPLY",
        },
    ]
    summary = module.summarize_answer_band_policy_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["missing_band_total"] == 0
    assert summary["high_risk_total"] == 4
    assert summary["policy_violation_total"] == 2
    assert abs(summary["safe_policy_coverage_ratio"] - 0.5) < 1e-9
    assert summary["forbidden_phrase_total"] == 2
    assert summary["missing_mandatory_phrase_total"] == 2
    assert summary["r3_execution_claim_total"] == 1
    assert summary["r3_handoff_missing_total"] == 1
    assert abs(summary["stale_minutes"] - (20.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_answer_band_policy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "safe_policy_coverage_ratio": 0.2,
            "missing_band_total": 2,
            "policy_violation_total": 3,
            "forbidden_phrase_total": 2,
            "missing_mandatory_phrase_total": 2,
            "r3_execution_claim_total": 1,
            "r3_handoff_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_safe_policy_coverage_ratio=0.95,
        max_missing_band_total=0,
        max_policy_violation_total=0,
        max_forbidden_phrase_total=0,
        max_missing_mandatory_phrase_total=0,
        max_r3_execution_claim_total=0,
        max_r3_handoff_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "safe_policy_coverage_ratio": 1.0,
            "missing_band_total": 0,
            "policy_violation_total": 0,
            "forbidden_phrase_total": 0,
            "missing_mandatory_phrase_total": 0,
            "r3_execution_claim_total": 0,
            "r3_handoff_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_safe_policy_coverage_ratio=0.0,
        max_missing_band_total=1000000,
        max_policy_violation_total=1000000,
        max_forbidden_phrase_total=1000000,
        max_missing_mandatory_phrase_total=1000000,
        max_r3_execution_claim_total=1000000,
        max_r3_handoff_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
