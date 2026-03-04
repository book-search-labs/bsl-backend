import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_replay_snapshot_format.py"
    spec = importlib.util.spec_from_file_location("chat_replay_snapshot_format", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_snapshot_format_tracks_required_fields():
    module = _load_module()
    rows = [
        {
            "recorded_at": "2026-03-03T00:00:00Z",
            "request_payload": {"message": "hi"},
            "policy_version": "v1",
            "prompt_template": "tpl-v1",
            "tool_calls": [{"name": "lookup"}],
            "budget_state": {"remaining_steps": 4},
            "seed": "seed-1",
        },
        {
            "recorded_at": "2026-03-03T00:01:00Z",
            "request_payload": None,
            "policy_version": "",
            "prompt_template": "",
            "tool_calls": [],
            "budget_state": {},
            "seed": "",
        },
    ]
    summary = module.summarize_snapshot_format(
        rows,
        now=datetime(2026, 3, 3, 0, 2, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 2
    assert summary["snapshot_total"] == 2
    assert summary["missing_request_payload_total"] == 1
    assert summary["missing_policy_version_total"] == 1
    assert summary["missing_prompt_template_total"] == 1
    assert summary["missing_tool_io_total"] == 1
    assert summary["missing_budget_state_total"] == 1
    assert summary["missing_seed_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_snapshot_format_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "missing_request_payload_total": 1,
            "missing_policy_version_total": 1,
            "missing_prompt_template_total": 1,
            "missing_tool_io_total": 1,
            "missing_budget_state_total": 1,
            "missing_seed_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_missing_request_payload_total=0,
        max_missing_policy_version_total=0,
        max_missing_prompt_template_total=0,
        max_missing_tool_io_total=0,
        max_missing_budget_state_total=0,
        max_missing_seed_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_request_payload_total": 0,
            "missing_policy_version_total": 0,
            "missing_prompt_template_total": 0,
            "missing_tool_io_total": 0,
            "missing_budget_state_total": 0,
            "missing_seed_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_request_payload_total=1000000,
        max_missing_policy_version_total=1000000,
        max_missing_prompt_template_total=1000000,
        max_missing_tool_io_total=1000000,
        max_missing_budget_state_total=1000000,
        max_missing_seed_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_snapshot_format_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "snapshot_total": 20,
            "missing_request_payload_total": 0,
            "missing_policy_version_total": 0,
            "missing_prompt_template_total": 0,
            "missing_tool_io_total": 0,
            "missing_budget_state_total": 0,
            "missing_seed_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "snapshot_total": 1,
            "missing_request_payload_total": 1,
            "missing_policy_version_total": 1,
            "missing_prompt_template_total": 1,
            "missing_tool_io_total": 1,
            "missing_budget_state_total": 1,
            "missing_seed_total": 1,
            "stale_minutes": 80.0,
        },
        max_snapshot_total_drop=1,
        max_missing_request_payload_total_increase=0,
        max_missing_policy_version_total_increase=0,
        max_missing_prompt_template_total_increase=0,
        max_missing_tool_io_total_increase=0,
        max_missing_budget_state_total_increase=0,
        max_missing_seed_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("snapshot_total regression" in item for item in failures)
    assert any("missing_request_payload_total regression" in item for item in failures)
    assert any("missing_policy_version_total regression" in item for item in failures)
    assert any("missing_prompt_template_total regression" in item for item in failures)
    assert any("missing_tool_io_total regression" in item for item in failures)
    assert any("missing_budget_state_total regression" in item for item in failures)
    assert any("missing_seed_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
