import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_correction_retrieval_integration.py"
    spec = importlib.util.spec_from_file_location("chat_correction_retrieval_integration", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_correction_retrieval_integration_tracks_precedence_and_conflict():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "correction_applied": True,
            "correction_override": True,
            "reason_code": "CORRECTION_OVERRIDE",
            "retrieval_latency_ms": 120,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "matched_correction_ids": ["c2"],
            "retrieval_route": "RAG_FIRST",
            "correction_applied": False,
            "policy_conflict": True,
            "safe_fallback_used": False,
            "retrieval_latency_ms": 300,
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "correction_hit": True,
            "correction_stale": True,
            "reason_code": "",
            "retrieval_latency_ms": 800,
        },
    ]
    summary = module.summarize_correction_retrieval_integration(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["request_total"] == 3
    assert summary["correction_hit_total"] == 2
    assert summary["hit_ratio"] == (2.0 / 3.0)
    assert summary["override_total"] == 1
    assert summary["stale_hit_total"] == 1
    assert summary["precedence_violation_total"] == 1
    assert summary["policy_conflict_total"] == 1
    assert summary["policy_conflict_unhandled_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["p95_retrieval_latency_ms"] == 800
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_correction_retrieval_integration_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "request_total": 1,
            "hit_ratio": 0.2,
            "stale_hit_total": 2,
            "precedence_violation_total": 3,
            "policy_conflict_unhandled_total": 1,
            "missing_reason_code_total": 2,
            "p95_retrieval_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_request_total=2,
        min_hit_ratio=0.9,
        max_stale_hit_total=0,
        max_precedence_violation_total=0,
        max_policy_conflict_unhandled_total=0,
        max_missing_reason_code_total=0,
        max_p95_retrieval_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "request_total": 0,
            "hit_ratio": 1.0,
            "stale_hit_total": 0,
            "precedence_violation_total": 0,
            "policy_conflict_unhandled_total": 0,
            "missing_reason_code_total": 0,
            "p95_retrieval_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_request_total=0,
        min_hit_ratio=0.0,
        max_stale_hit_total=1000000,
        max_precedence_violation_total=1000000,
        max_policy_conflict_unhandled_total=1000000,
        max_missing_reason_code_total=1000000,
        max_p95_retrieval_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_correction_retrieval_integration_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "request_total": 30,
            "correction_hit_total": 24,
            "hit_ratio": 0.80,
            "stale_hit_total": 0,
            "precedence_violation_total": 0,
            "policy_conflict_unhandled_total": 0,
            "missing_reason_code_total": 0,
            "p95_retrieval_latency_ms": 200.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "request_total": 1,
            "correction_hit_total": 1,
            "hit_ratio": 0.10,
            "stale_hit_total": 2,
            "precedence_violation_total": 2,
            "policy_conflict_unhandled_total": 1,
            "missing_reason_code_total": 1,
            "p95_retrieval_latency_ms": 1200.0,
            "stale_minutes": 90.0,
        },
        max_request_total_drop=1,
        max_correction_hit_total_drop=1,
        max_hit_ratio_drop=0.05,
        max_stale_hit_total_increase=0,
        max_precedence_violation_total_increase=0,
        max_policy_conflict_unhandled_total_increase=0,
        max_missing_reason_code_total_increase=0,
        max_p95_retrieval_latency_ms_increase=100.0,
        max_stale_minutes_increase=30.0,
    )
    assert any("request_total regression" in item for item in failures)
    assert any("correction_hit_total regression" in item for item in failures)
    assert any("hit_ratio regression" in item for item in failures)
    assert any("stale_hit_total regression" in item for item in failures)
    assert any("precedence_violation_total regression" in item for item in failures)
    assert any("policy_conflict_unhandled_total regression" in item for item in failures)
    assert any("missing_reason_code_total regression" in item for item in failures)
    assert any("p95_retrieval_latency_ms regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
