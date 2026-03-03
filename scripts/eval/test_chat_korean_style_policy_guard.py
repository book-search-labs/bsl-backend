import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_style_policy_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_style_policy_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_style_policy_guard_tracks_style_violations():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "style_checked": True,
            "response_text": "안녕하세요. 주문 상태를 확인해드리겠습니다.",
            "max_sentence_chars": 80,
            "tone_mode": "guidance",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "style_checked": True,
            "response_text": "환불 불가",
            "formal_required": True,
            "sentence_length_violation": True,
            "numeric_format_violation": True,
            "tone_mode": "restriction",
            "tone_violation": True,
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "style_checked": False,
            "response_text": "",
        },
    ]

    summary = module.summarize_korean_style_policy_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["response_total"] == 3
    assert summary["style_checked_total"] == 2
    assert abs(summary["style_checked_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["style_bypass_total"] == 1
    assert summary["style_violation_total"] == 1
    assert summary["style_compliance_ratio"] == 0.5
    assert summary["politeness_violation_total"] == 1
    assert summary["sentence_length_violation_total"] == 1
    assert summary["numeric_format_violation_total"] == 1
    assert summary["tone_violation_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_korean_style_policy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "response_total": 1,
            "style_checked_ratio": 0.4,
            "style_compliance_ratio": 0.2,
            "style_bypass_total": 3,
            "politeness_violation_total": 2,
            "sentence_length_violation_total": 2,
            "numeric_format_violation_total": 1,
            "tone_violation_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_response_total=2,
        min_style_checked_ratio=0.95,
        min_style_compliance_ratio=0.95,
        max_style_bypass_total=0,
        max_politeness_violation_total=0,
        max_sentence_length_violation_total=0,
        max_numeric_format_violation_total=0,
        max_tone_violation_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "response_total": 0,
            "style_checked_ratio": 1.0,
            "style_compliance_ratio": 1.0,
            "style_bypass_total": 0,
            "politeness_violation_total": 0,
            "sentence_length_violation_total": 0,
            "numeric_format_violation_total": 0,
            "tone_violation_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_response_total=0,
        min_style_checked_ratio=0.0,
        min_style_compliance_ratio=0.0,
        max_style_bypass_total=1000000,
        max_politeness_violation_total=1000000,
        max_sentence_length_violation_total=1000000,
        max_numeric_format_violation_total=1000000,
        max_tone_violation_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
