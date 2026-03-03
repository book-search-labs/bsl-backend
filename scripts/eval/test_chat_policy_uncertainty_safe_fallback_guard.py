import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_policy_uncertainty_safe_fallback_guard.py"
    spec = importlib.util.spec_from_file_location("chat_policy_uncertainty_safe_fallback_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_policy_uncertainty_safe_fallback_guard_tracks_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "reason_code": "POLICY_UNCERTAIN",
            "answer_text": "정책 확인이 필요합니다. 고객센터로 문의해 주세요.",
            "status": "insufficient_evidence",
            "next_action": "OPEN_SUPPORT_TICKET",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "policy_uncertain": True,
            "answer_text": "이 요청은 무조건 처리 완료됩니다.",
            "status": "ok",
            "next_action": "NONE",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "policy_uncertain": True,
            "safe_guidance_present": False,
            "definitive_claim_present": False,
            "fallback_downgraded": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "policy_uncertain": False,
            "answer_text": "정상 응답",
            "status": "ok",
        },
    ]
    summary = module.summarize_policy_uncertainty_safe_fallback_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["policy_uncertain_total"] == 3
    assert summary["unsafe_definitive_total"] == 1
    assert summary["safe_guidance_missing_total"] == 2
    assert summary["fallback_downgrade_missing_total"] == 1
    assert abs(summary["uncertainty_safe_ratio"] - (1.0 / 3.0)) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_policy_uncertainty_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "uncertainty_safe_ratio": 0.25,
            "unsafe_definitive_total": 2,
            "safe_guidance_missing_total": 1,
            "fallback_downgrade_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_uncertainty_safe_ratio=0.95,
        max_unsafe_definitive_total=0,
        max_safe_guidance_missing_total=0,
        max_fallback_downgrade_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "uncertainty_safe_ratio": 1.0,
            "unsafe_definitive_total": 0,
            "safe_guidance_missing_total": 0,
            "fallback_downgrade_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_uncertainty_safe_ratio=0.0,
        max_unsafe_definitive_total=1000000,
        max_safe_guidance_missing_total=1000000,
        max_fallback_downgrade_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
