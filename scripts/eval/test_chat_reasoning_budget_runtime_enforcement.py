import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_reasoning_budget_runtime_enforcement.py"
    spec = importlib.util.spec_from_file_location("chat_reasoning_budget_runtime_enforcement", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_runtime_enforcement_tracks_abort_and_breach():
    module = _load_module()
    rows = [
        {"request_id": "r1", "timestamp": "2026-03-03T00:00:00Z", "event_type": "budget_warning"},
        {
            "request_id": "r1",
            "timestamp": "2026-03-03T00:00:01Z",
            "event_type": "budget_exceeded",
            "budget_type": "token",
            "enforcement_action": "EARLY_STOP",
        },
        {"request_id": "r1", "timestamp": "2026-03-03T00:00:02Z", "event_type": "budget_abort", "graceful": True},
        {"request_id": "r1", "timestamp": "2026-03-03T00:00:03Z", "event_type": "retry_prompt"},
        {"request_id": "r2", "timestamp": "2026-03-03T00:01:00Z", "event_type": "budget_exceeded", "budget_type": "step"},
        {"request_id": "r3", "timestamp": "2026-03-03T00:02:00Z", "event_type": "hard_breach"},
    ]
    summary = module.summarize_runtime_enforcement(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 6
    assert summary["request_total"] == 3
    assert summary["exceeded_request_total"] == 2
    assert summary["abort_request_total"] == 1
    assert summary["warning_before_abort_total"] == 1
    assert summary["unhandled_exceed_request_total"] == 1
    assert summary["hard_breach_total"] == 1
    assert abs(summary["enforcement_coverage_ratio"] - 0.5) < 1e-9
    assert abs(summary["retry_prompt_ratio"] - 1.0) < 1e-9


def test_evaluate_gate_detects_runtime_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "hard_breach_total": 2,
            "unhandled_exceed_request_total": 3,
            "enforcement_coverage_ratio": 0.2,
            "warning_before_abort_ratio": 0.3,
            "graceful_abort_ratio": 0.4,
            "retry_prompt_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_window=20,
        max_hard_breach_total=0,
        max_unhandled_exceed_request_total=0,
        min_enforcement_coverage_ratio=0.95,
        min_warning_before_abort_ratio=0.7,
        min_graceful_abort_ratio=0.9,
        min_retry_prompt_ratio=0.8,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_window_with_open_threshold():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "hard_breach_total": 0,
            "unhandled_exceed_request_total": 0,
            "enforcement_coverage_ratio": 1.0,
            "warning_before_abort_ratio": 1.0,
            "graceful_abort_ratio": 1.0,
            "retry_prompt_ratio": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_hard_breach_total=1000000,
        max_unhandled_exceed_request_total=1000000,
        min_enforcement_coverage_ratio=0.0,
        min_warning_before_abort_ratio=0.0,
        min_graceful_abort_ratio=0.0,
        min_retry_prompt_ratio=0.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_runtime_enforcement_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "hard_breach_total": 0,
            "unhandled_exceed_request_total": 0,
            "enforcement_coverage_ratio": 1.0,
            "warning_before_abort_ratio": 1.0,
            "graceful_abort_ratio": 1.0,
            "retry_prompt_ratio": 1.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "hard_breach_total": 3,
            "unhandled_exceed_request_total": 2,
            "enforcement_coverage_ratio": 0.4,
            "warning_before_abort_ratio": 0.3,
            "graceful_abort_ratio": 0.2,
            "retry_prompt_ratio": 0.5,
            "stale_minutes": 80.0,
        },
        max_hard_breach_total_increase=0,
        max_unhandled_exceed_request_total_increase=0,
        max_enforcement_coverage_ratio_drop=0.05,
        max_warning_before_abort_ratio_drop=0.05,
        max_graceful_abort_ratio_drop=0.05,
        max_retry_prompt_ratio_drop=0.05,
        max_stale_minutes_increase=30.0,
    )
    assert any("hard_breach_total regression" in item for item in failures)
    assert any("unhandled_exceed_request_total regression" in item for item in failures)
    assert any("enforcement_coverage_ratio regression" in item for item in failures)
    assert any("warning_before_abort_ratio regression" in item for item in failures)
    assert any("graceful_abort_ratio regression" in item for item in failures)
    assert any("retry_prompt_ratio regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
