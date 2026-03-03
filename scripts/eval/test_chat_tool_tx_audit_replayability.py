import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_tx_audit_replayability.py"
    spec = importlib.util.spec_from_file_location("chat_tool_tx_audit_replayability", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_tx_audit_replayability_tracks_required_fields_and_replayability():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "tx_id": "tx1",
            "phase": "prepare",
            "trace_id": "t1",
            "request_id": "r1",
            "reason_code": "START",
        },
        {
            "timestamp": "2026-03-03T00:00:05Z",
            "tx_id": "tx1",
            "phase": "validate",
            "trace_id": "t1",
            "request_id": "r1",
            "reason_code": "VALID",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "tx_id": "tx1",
            "phase": "commit",
            "trace_id": "t1",
            "request_id": "r1",
            "reason_code": "DONE",
            "action_type": "WRITE",
            "actor_id": "u1",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "tx_id": "tx2",
            "phase": "prepare",
            "trace_id": "t2",
            "request_id": "r2",
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "tx_id": "tx2",
            "phase": "compensation_failed",
            "trace_id": "",
            "request_id": "r2",
            "reason_code": "ERR",
            "action_type": "WRITE_SENSITIVE",
            "actor_id": "",
        },
        {
            "timestamp": "2026-03-03T00:00:40Z",
            "tx_id": "tx3",
            "phase": "",
            "trace_id": "t3",
            "request_id": "r3",
            "reason_code": "UNKNOWN",
        },
    ]

    summary = module.summarize_tool_tx_audit_replayability(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 6
    assert summary["tx_total"] == 3
    assert summary["replayable_tx_total"] == 1
    assert summary["non_replayable_tx_total"] == 2
    assert summary["replayable_ratio"] == (1.0 / 3.0)
    assert summary["missing_trace_id_total"] == 1
    assert summary["missing_request_id_total"] == 0
    assert summary["missing_reason_code_total"] == 1
    assert summary["missing_phase_total"] == 1
    assert summary["missing_actor_total"] == 1
    assert summary["transition_gap_total"] == 1
    assert summary["p95_replay_span_ms"] == 10000.0
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_audit_replayability_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "tx_total": 1,
            "replayable_ratio": 0.1,
            "missing_trace_id_total": 2,
            "missing_request_id_total": 1,
            "missing_reason_code_total": 3,
            "missing_phase_total": 1,
            "missing_actor_total": 2,
            "transition_gap_total": 4,
            "non_replayable_tx_total": 2,
            "p95_replay_span_ms": 4500.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_tx_total=2,
        min_replayable_ratio=0.95,
        max_missing_trace_id_total=0,
        max_missing_request_id_total=0,
        max_missing_reason_code_total=0,
        max_missing_phase_total=0,
        max_missing_actor_total=0,
        max_transition_gap_total=0,
        max_non_replayable_tx_total=0,
        max_p95_replay_span_ms=1500.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 12


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "tx_total": 0,
            "replayable_ratio": 1.0,
            "missing_trace_id_total": 0,
            "missing_request_id_total": 0,
            "missing_reason_code_total": 0,
            "missing_phase_total": 0,
            "missing_actor_total": 0,
            "transition_gap_total": 0,
            "non_replayable_tx_total": 0,
            "p95_replay_span_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_tx_total=0,
        min_replayable_ratio=0.0,
        max_missing_trace_id_total=1000000,
        max_missing_request_id_total=1000000,
        max_missing_reason_code_total=1000000,
        max_missing_phase_total=1000000,
        max_missing_actor_total=1000000,
        max_transition_gap_total=1000000,
        max_non_replayable_tx_total=1000000,
        max_p95_replay_span_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
