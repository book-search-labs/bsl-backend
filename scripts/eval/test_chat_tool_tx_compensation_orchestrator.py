import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_tx_compensation_orchestrator.py"
    spec = importlib.util.spec_from_file_location("chat_tool_tx_compensation_orchestrator", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_tx_compensation_orchestrator_tracks_failures_and_safety_controls():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "tx_id": "tx1", "event_type": "partial_failure"},
        {"timestamp": "2026-03-03T00:00:05Z", "tx_id": "tx1", "event_type": "compensation_started"},
        {"timestamp": "2026-03-03T00:00:10Z", "tx_id": "tx1", "event_type": "compensation_succeeded"},
        {"timestamp": "2026-03-03T00:00:20Z", "tx_id": "tx2", "event_type": "partial_failure"},
        {"timestamp": "2026-03-03T00:00:30Z", "tx_id": "tx2", "event_type": "compensation_failed"},
        {"timestamp": "2026-03-03T00:00:40Z", "tx_id": "tx3", "event_type": "compensation_started"},
    ]

    summary = module.summarize_tool_tx_compensation_orchestrator(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 6
    assert summary["tx_total"] == 3
    assert summary["compensation_required_total"] == 2
    assert summary["compensation_started_total"] == 2
    assert summary["compensation_succeeded_total"] == 1
    assert summary["compensation_failed_total"] == 1
    assert summary["compensation_missing_total"] == 0
    assert summary["safe_stop_missing_total"] == 1
    assert summary["operator_alert_missing_total"] == 1
    assert summary["orphan_compensation_total"] == 1
    assert summary["compensation_success_ratio"] == 0.5
    assert summary["compensation_resolution_ratio"] == 1.0
    assert summary["p95_failure_to_compensation_latency_ms"] == 10000.0
    assert summary["p95_compensation_resolution_latency_ms"] == 10000.0
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_compensation_orchestrator_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "compensation_required_total": 1,
            "compensation_success_ratio": 0.1,
            "compensation_resolution_ratio": 0.2,
            "compensation_failed_total": 2,
            "compensation_missing_total": 3,
            "safe_stop_missing_total": 1,
            "operator_alert_missing_total": 1,
            "orphan_compensation_total": 2,
            "p95_failure_to_compensation_latency_ms": 2500.0,
            "p95_compensation_resolution_latency_ms": 4500.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_compensation_required_total=2,
        min_compensation_success_ratio=0.95,
        min_compensation_resolution_ratio=0.99,
        max_compensation_failed_total=0,
        max_compensation_missing_total=0,
        max_safe_stop_missing_total=0,
        max_operator_alert_missing_total=0,
        max_orphan_compensation_total=0,
        max_p95_failure_to_compensation_latency_ms=1500.0,
        max_p95_compensation_resolution_latency_ms=2000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 12


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "compensation_required_total": 0,
            "compensation_success_ratio": 1.0,
            "compensation_resolution_ratio": 1.0,
            "compensation_failed_total": 0,
            "compensation_missing_total": 0,
            "safe_stop_missing_total": 0,
            "operator_alert_missing_total": 0,
            "orphan_compensation_total": 0,
            "p95_failure_to_compensation_latency_ms": 0.0,
            "p95_compensation_resolution_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_compensation_required_total=0,
        min_compensation_success_ratio=0.0,
        min_compensation_resolution_ratio=0.0,
        max_compensation_failed_total=1000000,
        max_compensation_missing_total=1000000,
        max_safe_stop_missing_total=1000000,
        max_operator_alert_missing_total=1000000,
        max_orphan_compensation_total=1000000,
        max_p95_failure_to_compensation_latency_ms=1000000.0,
        max_p95_compensation_resolution_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
