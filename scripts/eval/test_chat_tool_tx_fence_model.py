import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_tx_fence_model.py"
    spec = importlib.util.spec_from_file_location("chat_tool_tx_fence_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_tx_fence_model_tracks_sequence_and_optimistic_check():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "tx_id": "t1", "phase": "prepare"},
        {"timestamp": "2026-03-03T00:00:10Z", "tx_id": "t1", "phase": "validate"},
        {"timestamp": "2026-03-03T00:00:20Z", "tx_id": "t1", "phase": "commit", "optimistic_check_passed": True},
        {"timestamp": "2026-03-03T00:01:00Z", "tx_id": "t2", "phase": "commit", "optimistic_check_passed": False},
        {"timestamp": "2026-03-03T00:02:00Z", "tx_id": "t3", "phase": "prepare"},
        {"timestamp": "2026-03-03T00:02:10Z", "tx_id": "t3", "phase": "validate"},
        {"timestamp": "2026-03-03T00:02:20Z", "tx_id": "t3", "phase": "commit"},
        {"timestamp": "2026-03-03T00:02:30Z", "tx_id": "t3", "phase": "abort"},
        {"timestamp": "2026-03-03T00:02:40Z", "tx_id": "t3", "phase": "validate", "inconsistent_state_detected": True},
    ]
    summary = module.summarize_tool_tx_fence_model(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 9
    assert summary["tx_total"] == 3
    assert summary["tx_committed_total"] == 3
    assert summary["tx_aborted_total"] == 1
    assert summary["sequence_violation_total"] == 1
    assert summary["optimistic_check_missing_total"] == 1
    assert summary["optimistic_mismatch_commit_total"] == 1
    assert summary["inconsistent_state_total"] == 1
    assert summary["commit_after_validate_ratio"] == (2.0 / 3.0)
    assert summary["p95_prepare_to_commit_latency_ms"] == 20000
    assert summary["stale_minutes"] == (20.0 / 60.0)


def test_evaluate_gate_detects_tool_tx_fence_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "tx_total": 1,
            "commit_after_validate_ratio": 0.2,
            "sequence_violation_total": 2,
            "optimistic_check_missing_total": 1,
            "optimistic_mismatch_commit_total": 1,
            "inconsistent_state_total": 1,
            "p95_prepare_to_commit_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_tx_total=2,
        min_commit_after_validate_ratio=0.95,
        max_sequence_violation_total=0,
        max_optimistic_check_missing_total=0,
        max_optimistic_mismatch_commit_total=0,
        max_inconsistent_state_total=0,
        max_p95_prepare_to_commit_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "tx_total": 0,
            "commit_after_validate_ratio": 1.0,
            "sequence_violation_total": 0,
            "optimistic_check_missing_total": 0,
            "optimistic_mismatch_commit_total": 0,
            "inconsistent_state_total": 0,
            "p95_prepare_to_commit_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_tx_total=0,
        min_commit_after_validate_ratio=0.0,
        max_sequence_violation_total=1000000,
        max_optimistic_check_missing_total=1000000,
        max_optimistic_mismatch_commit_total=1000000,
        max_inconsistent_state_total=1000000,
        max_p95_prepare_to_commit_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
