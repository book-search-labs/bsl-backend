import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_policy_eval_trace.py"
    spec = importlib.util.spec_from_file_location("chat_policy_eval_trace", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_policy_eval_trace_flags_nondeterministic_and_unresolved_conflict():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "policy_eval",
            "request_id": "r1",
            "policy_version": "policy-v1",
            "matched_rule_ids": ["rule-1"],
            "final_action": "allow",
            "eval_key": "key-1",
            "latency_ms": 100,
        },
        {
            "timestamp": "2026-03-03T00:00:01Z",
            "event_type": "policy_eval",
            "request_id": "r2",
            "policy_version": "policy-v1",
            "matched_rule_ids": ["rule-2"],
            "final_action": "deny",
            "eval_key": "key-1",
            "latency_ms": 120,
        },
        {
            "timestamp": "2026-03-03T00:00:02Z",
            "event_type": "policy_conflict",
            "request_id": "",
            "policy_version": "",
            "matched_rule_ids": [],
            "final_action": "UNKNOWN_ACTION",
            "conflict_detected": True,
            "latency_ms": 150,
        },
    ]
    summary = module.summarize_policy_eval_trace(rows, now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc))
    assert summary["eval_total"] == 3
    assert summary["missing_request_id_total"] == 1
    assert summary["missing_policy_version_total"] == 1
    assert summary["missing_matched_rule_total"] == 1
    assert summary["unknown_final_action_total"] == 1
    assert summary["non_deterministic_key_total"] == 1
    assert summary["conflict_total"] == 1
    assert summary["conflict_unresolved_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "missing_request_id_total": 1,
            "missing_policy_version_total": 1,
            "missing_matched_rule_total": 1,
            "unknown_final_action_total": 1,
            "non_deterministic_key_total": 1,
            "conflict_unresolved_total": 1,
            "latency_p95_ms": 2500.0,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_missing_request_id_total=0,
        max_missing_policy_version_total=0,
        max_missing_matched_rule_total=0,
        max_unknown_final_action_total=0,
        max_non_deterministic_key_total=0,
        max_conflict_unresolved_total=0,
        max_latency_p95_ms=2000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_request_id_total": 0,
            "missing_policy_version_total": 0,
            "missing_matched_rule_total": 0,
            "unknown_final_action_total": 0,
            "non_deterministic_key_total": 0,
            "conflict_unresolved_total": 0,
            "latency_p95_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_request_id_total=0,
        max_missing_policy_version_total=0,
        max_missing_matched_rule_total=0,
        max_unknown_final_action_total=0,
        max_non_deterministic_key_total=0,
        max_conflict_unresolved_total=0,
        max_latency_p95_ms=2000.0,
        max_stale_minutes=60.0,
    )
    assert failures == []
