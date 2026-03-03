import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_sensitive_action_risk_classification.py"
    spec = importlib.util.spec_from_file_location("chat_sensitive_action_risk_classification", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_risk_classification_flags_high_without_stepup():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "risk_level": "HIGH",
            "stepup_required": False,
            "irreversible": True,
            "actor_id": "u1",
            "target_id": "o1",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "risk_level": "LOW",
            "stepup_required": False,
            "irreversible": True,
            "actor_id": "",
            "target_id": "",
        },
    ]
    summary = module.summarize_risk_classification(rows, now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc))
    assert summary["action_total"] == 2
    assert summary["high_risk_without_stepup_total"] == 1
    assert summary["irreversible_not_high_risk_total"] == 1
    assert summary["missing_actor_total"] == 1
    assert summary["missing_target_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "unknown_risk_total": 1,
            "high_risk_without_stepup_total": 1,
            "irreversible_not_high_risk_total": 1,
            "missing_actor_total": 1,
            "missing_target_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_unknown_risk_total=0,
        max_high_risk_without_stepup_total=0,
        max_irreversible_not_high_risk_total=0,
        max_missing_actor_total=0,
        max_missing_target_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "unknown_risk_total": 0,
            "high_risk_without_stepup_total": 0,
            "irreversible_not_high_risk_total": 0,
            "missing_actor_total": 0,
            "missing_target_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_unknown_risk_total=0,
        max_high_risk_without_stepup_total=0,
        max_irreversible_not_high_risk_total=0,
        max_missing_actor_total=0,
        max_missing_target_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_sensitive_risk_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "unknown_risk_total": 0,
                "high_risk_without_stepup_total": 0,
                "irreversible_not_high_risk_total": 0,
                "missing_actor_total": 0,
                "missing_target_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "unknown_risk_total": 1,
            "high_risk_without_stepup_total": 1,
            "irreversible_not_high_risk_total": 1,
            "missing_actor_total": 1,
            "missing_target_total": 1,
            "stale_minutes": 40.0,
        },
        max_unknown_risk_total_increase=0,
        max_high_risk_without_stepup_total_increase=0,
        max_irreversible_not_high_risk_total_increase=0,
        max_missing_actor_total_increase=0,
        max_missing_target_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 6
