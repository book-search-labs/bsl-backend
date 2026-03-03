import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_answer_tiered_approval_flow_guard.py"
    spec = importlib.util.spec_from_file_location("chat_answer_tiered_approval_flow_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_answer_tiered_approval_flow_guard_tracks_high_risk_routing():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-04T00:00:00Z", "risk_band": "R0", "approval_action": "AUTO_REPLY"},
        {"timestamp": "2026-03-04T00:00:05Z", "risk_band": "R1", "approval_action": "AUTO_REPLY"},
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "risk_band": "R2",
            "approval_action": "APPROVAL_QUEUE",
            "approval_queue_id": "q-1",
        },
        {"timestamp": "2026-03-04T00:00:15Z", "risk_band": "R2", "approval_action": "AUTO_REPLY"},
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "risk_band": "R3",
            "approval_action": "HUMAN_APPROVAL",
            "approval_queue_id": "q-2",
        },
        {"timestamp": "2026-03-04T00:00:25Z", "risk_band": "R3", "approval_action": "AUTO_REPLY"},
        {"timestamp": "2026-03-04T00:00:30Z", "risk_band": "R2", "approval_action": "APPROVAL_QUEUE"},
    ]
    summary = module.summarize_answer_tiered_approval_flow_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 7
    assert summary["event_total"] == 7
    assert summary["missing_band_total"] == 0
    assert summary["high_risk_total"] == 5
    assert summary["approval_routed_total"] == 3
    assert abs(summary["high_risk_approval_coverage_ratio"] - 0.6) < 1e-9
    assert summary["unsafe_auto_high_risk_total"] == 2
    assert summary["r3_auto_total"] == 1
    assert summary["approval_queue_missing_total"] == 1
    assert summary["low_risk_total"] == 2
    assert summary["low_risk_auto_total"] == 2
    assert abs(summary["low_risk_auto_ratio"] - 1.0) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_tiered_approval_flow_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "high_risk_approval_coverage_ratio": 0.2,
            "low_risk_auto_ratio": 0.1,
            "missing_band_total": 2,
            "unsafe_auto_high_risk_total": 2,
            "r3_auto_total": 1,
            "approval_queue_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_high_risk_approval_coverage_ratio=0.9,
        min_low_risk_auto_ratio=0.9,
        max_missing_band_total=0,
        max_unsafe_auto_high_risk_total=0,
        max_r3_auto_total=0,
        max_approval_queue_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "high_risk_approval_coverage_ratio": 1.0,
            "low_risk_auto_ratio": 1.0,
            "missing_band_total": 0,
            "unsafe_auto_high_risk_total": 0,
            "r3_auto_total": 0,
            "approval_queue_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_high_risk_approval_coverage_ratio=0.0,
        min_low_risk_auto_ratio=0.0,
        max_missing_band_total=1000000,
        max_unsafe_auto_high_risk_total=1000000,
        max_r3_auto_total=1000000,
        max_approval_queue_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
