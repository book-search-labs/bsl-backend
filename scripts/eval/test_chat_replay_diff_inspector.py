import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_replay_diff_inspector.py"
    spec = importlib.util.spec_from_file_location("chat_replay_diff_inspector", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_diff_inspector_tracks_divergence_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "matched": True,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "divergence_detected": True,
            "first_divergence": {"type": "POLICY", "step": 1},
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "status": "MISMATCH",
            "diff": {"first_divergence": {"type": "TOOL_IO", "step": 2}},
        },
        {
            "timestamp": "2026-03-03T00:04:00Z",
            "matched": False,
        },
        {
            "timestamp": "2026-03-03T00:05:00Z",
            "divergence_detected": True,
            "first_divergence": {"type": "WEIRD", "step": 0},
        },
    ]
    summary = module.summarize_diff_inspector(
        rows,
        now=datetime(2026, 3, 3, 0, 6, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["run_total"] == 5
    assert summary["matched_total"] == 1
    assert summary["divergence_detected_total"] == 4
    assert summary["first_divergence_total"] == 3
    assert summary["missing_first_divergence_total"] == 1
    assert summary["unknown_divergence_type_total"] == 1
    assert summary["invalid_step_total"] == 1
    assert summary["stale_minutes"] == 1.0

    distribution = {row["type"]: row["count"] for row in summary["divergence_type_distribution"]}
    assert distribution["POLICY"] == 1
    assert distribution["TOOL_IO"] == 1
    assert distribution["WEIRD"] == 1


def test_evaluate_gate_detects_diff_inspector_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "divergence_detected_total": 2,
            "missing_first_divergence_total": 1,
            "unknown_divergence_type_total": 1,
            "invalid_step_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_divergence_detected_total=3,
        max_missing_first_divergence_total=0,
        max_unknown_divergence_type_total=0,
        max_invalid_step_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_when_minimum_is_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "divergence_detected_total": 0,
            "missing_first_divergence_total": 0,
            "unknown_divergence_type_total": 0,
            "invalid_step_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_divergence_detected_total=0,
        max_missing_first_divergence_total=1000000,
        max_unknown_divergence_type_total=1000000,
        max_invalid_step_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
