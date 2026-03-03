import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_workflow_state_model.py"
    spec = importlib.util.spec_from_file_location("chat_workflow_state_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_workflow_state_counts_templates_and_fields():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "workflow_id": "w1",
            "workflow_type": "CANCEL_ORDER",
            "current_step": "collect_order_id",
            "required_inputs": ["order_id"],
            "last_action_at": "2026-03-03T00:00:00Z",
            "checkpoint_id": "cp1",
            "event_type": "STARTED",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "workflow_id": "w2",
            "workflow_type": "UNKNOWN_FLOW",
            "current_step": "",
            "required_inputs": ["reason"],
            "last_action_at": "",
            "event_type": "STARTED",
        },
    ]
    summary = module.summarize_workflow_state(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 2
    assert summary["workflow_total"] == 2
    assert summary["missing_state_fields_total"] == 1
    assert summary["unsupported_type_total"] == 1
    assert summary["checkpoint_ratio"] == 0.5


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "missing_state_fields_total": 2,
            "unsupported_type_total": 1,
            "checkpoint_ratio": 0.3,
            "stale_minutes": 120.0,
            "missing_templates": ["REFUND_REQUEST"],
        },
        min_window=1,
        max_missing_state_fields_total=0,
        max_unsupported_type_total=0,
        min_checkpoint_ratio=0.8,
        max_stale_minutes=60.0,
        require_templates=True,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "missing_state_fields_total": 0,
            "unsupported_type_total": 0,
            "checkpoint_ratio": 1.0,
            "stale_minutes": 5.0,
            "missing_templates": [],
        },
        min_window=1,
        max_missing_state_fields_total=0,
        max_unsupported_type_total=0,
        min_checkpoint_ratio=0.8,
        max_stale_minutes=60.0,
        require_templates=True,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_state_fields_total": 0,
            "unsupported_type_total": 0,
            "checkpoint_ratio": 0.0,
            "stale_minutes": 0.0,
            "missing_templates": [],
        },
        min_window=0,
        max_missing_state_fields_total=0,
        max_unsupported_type_total=0,
        min_checkpoint_ratio=0.8,
        max_stale_minutes=60.0,
        require_templates=False,
    )
    assert failures == []
