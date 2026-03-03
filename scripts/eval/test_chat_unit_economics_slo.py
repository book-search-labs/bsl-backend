import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_unit_economics_slo.py"
    spec = importlib.util.spec_from_file_location("chat_unit_economics_slo", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_unit_economics_tracks_cost_mix_and_resolution():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": "2026-03-03T11:00:00Z",
            "intent": "ORDER_STATUS",
            "resolved": True,
            "session_cost_usd": 1.2,
            "tool_cost_usd": 0.4,
            "token_cost_usd": 0.8,
        },
        {
            "timestamp": "2026-03-03T11:10:00Z",
            "intent": "REFUND_REQUEST",
            "resolved": False,
            "session_cost_usd": 2.0,
            "tool_cost_usd": 1.0,
            "token_cost_usd": 1.0,
        },
    ]
    summary = module.summarize_unit_economics(rows, now=now)
    assert summary["window_size"] == 2
    assert summary["resolved_total"] == 1
    assert summary["unresolved_total"] == 1
    assert summary["resolution_rate"] == 0.5
    assert summary["cost_per_resolved_session"] == 1.2
    assert summary["tool_cost_mix_ratio"] > 0


def test_evaluate_gate_detects_violations():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "resolution_rate": 0.5,
            "cost_per_resolved_session": 3.0,
            "unresolved_cost_burn_total": 300.0,
            "tool_cost_mix_ratio": 0.9,
            "stale_days": 10,
        },
        min_window=1,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.0,
        max_unresolved_cost_burn_total=200.0,
        max_tool_cost_mix_ratio=0.8,
        max_stale_days=8,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_metrics_are_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "resolution_rate": 0.9,
            "cost_per_resolved_session": 1.0,
            "unresolved_cost_burn_total": 20.0,
            "tool_cost_mix_ratio": 0.4,
            "stale_days": 2,
        },
        min_window=1,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.0,
        max_unresolved_cost_burn_total=200.0,
        max_tool_cost_mix_ratio=0.8,
        max_stale_days=8,
    )
    assert failures == []


def test_evaluate_gate_skips_ratio_checks_when_window_empty():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "resolution_rate": 0.0,
            "cost_per_resolved_session": 0.0,
            "unresolved_cost_burn_total": 0.0,
            "tool_cost_mix_ratio": 0.0,
            "stale_days": 0.0,
        },
        min_window=0,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.0,
        max_unresolved_cost_burn_total=200.0,
        max_tool_cost_mix_ratio=0.8,
        max_stale_days=8,
    )
    assert failures == []


def test_compare_with_baseline_detects_resolution_cost_and_mix_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "resolution_rate": 0.90,
                "cost_per_resolved_session": 1.00,
                "unresolved_cost_burn_total": 20.0,
                "tool_cost_mix_ratio": 0.40,
                "token_cost_mix_ratio": 0.45,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "resolution_rate": 0.80,
            "cost_per_resolved_session": 1.70,
            "unresolved_cost_burn_total": 90.0,
            "tool_cost_mix_ratio": 0.55,
            "token_cost_mix_ratio": 0.60,
        },
        max_resolution_rate_drop=0.05,
        max_cost_per_resolved_session_increase=0.50,
        max_unresolved_cost_burn_total_increase=50.0,
        max_tool_cost_mix_ratio_increase=0.10,
        max_token_cost_mix_ratio_increase=0.10,
    )
    assert len(failures) == 5
