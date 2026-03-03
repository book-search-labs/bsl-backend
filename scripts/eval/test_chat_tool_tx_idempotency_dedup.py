import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_tx_idempotency_dedup.py"
    spec = importlib.util.spec_from_file_location("chat_tool_tx_idempotency_dedup", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_tx_idempotency_dedup_tracks_missing_keys_and_duplicates():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "action_type": "WRITE",
            "idempotency_key": "k1",
            "payload_hash": "h1",
            "side_effect_applied": True,
            "is_retry": False,
            "retry_resolution_latency_ms": 100,
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "action_type": "WRITE",
            "idempotency_key": "k1",
            "payload_hash": "h2",
            "side_effect_applied": True,
            "is_retry": True,
            "dedup_hit": False,
            "retry_resolution_latency_ms": 300,
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "action_type": "WRITE_SENSITIVE",
            "idempotency_key": "",
            "is_retry": True,
            "dedup_result": "HIT",
            "retry_resolution_latency_ms": 500,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "action_type": "READ",
            "idempotency_key": "",
            "is_retry": True,
        },
    ]
    summary = module.summarize_tool_tx_idempotency_dedup(
        rows,
        now=datetime(2026, 3, 3, 0, 2, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["tool_call_total"] == 4
    assert summary["write_call_total"] == 3
    assert summary["missing_idempotency_key_total"] == 1
    assert summary["retry_call_total"] == 2
    assert summary["dedup_hit_total"] == 1
    assert summary["retry_safe_ratio"] == 0.5
    assert summary["duplicate_side_effect_total"] == 1
    assert summary["key_reuse_cross_payload_total"] == 1
    assert summary["p95_retry_resolution_latency_ms"] == 500
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_tool_tx_idempotency_dedup_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "write_call_total": 1,
            "retry_safe_ratio": 0.2,
            "missing_idempotency_key_total": 2,
            "duplicate_side_effect_total": 3,
            "key_reuse_cross_payload_total": 1,
            "p95_retry_resolution_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_write_call_total=2,
        min_retry_safe_ratio=0.9,
        max_missing_idempotency_key_total=0,
        max_duplicate_side_effect_total=0,
        max_key_reuse_cross_payload_total=0,
        max_p95_retry_resolution_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "write_call_total": 0,
            "retry_safe_ratio": 1.0,
            "missing_idempotency_key_total": 0,
            "duplicate_side_effect_total": 0,
            "key_reuse_cross_payload_total": 0,
            "p95_retry_resolution_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_write_call_total=0,
        min_retry_safe_ratio=0.0,
        max_missing_idempotency_key_total=1000000,
        max_duplicate_side_effect_total=1000000,
        max_key_reuse_cross_payload_total=1000000,
        max_p95_retry_resolution_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
