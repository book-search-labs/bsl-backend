import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_config_audit_reproducibility.py"
    spec = importlib.util.spec_from_file_location("chat_config_audit_reproducibility", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_audit_reproducibility_counts_missing_fields(tmp_path: Path):
    module = _load_module()
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / "s1.json").write_text('{"ok":true}', encoding="utf-8")

    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "actor": "u1",
            "bundle_id": "b1",
            "request_id": "r1",
            "trace_id": "t1",
            "immutable": True,
            "snapshot_id": "s1",
            "diff_hash": "h1",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "actor": "",
            "bundle_id": "b2",
            "request_id": "r2",
            "trace_id": "",
            "immutable": False,
            "snapshot_id": "missing",
            "diff_hash": "",
        },
    ]
    summary = module.summarize_audit_reproducibility(
        rows,
        snapshots_dir=snapshots_dir,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 2
    assert summary["missing_actor_total"] == 1
    assert summary["missing_trace_total"] == 1
    assert summary["immutable_violation_total"] == 1
    assert summary["snapshot_ref_total"] == 2
    assert summary["snapshot_replayable_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "missing_actor_total": 2,
            "missing_trace_total": 1,
            "immutable_violation_total": 1,
            "snapshot_replay_ratio": 0.5,
            "diff_coverage_ratio": 0.6,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_missing_actor_total=0,
        max_missing_trace_total=0,
        max_immutable_violation_total=0,
        min_snapshot_replay_ratio=0.95,
        min_diff_coverage_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_passes_healthy_summary():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "missing_actor_total": 0,
            "missing_trace_total": 0,
            "immutable_violation_total": 0,
            "snapshot_replay_ratio": 1.0,
            "diff_coverage_ratio": 1.0,
            "stale_minutes": 10.0,
        },
        min_window=1,
        max_missing_actor_total=0,
        max_missing_trace_total=0,
        max_immutable_violation_total=0,
        min_snapshot_replay_ratio=0.95,
        min_diff_coverage_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_when_min_window_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_actor_total": 0,
            "missing_trace_total": 0,
            "immutable_violation_total": 0,
            "snapshot_replay_ratio": 0.0,
            "diff_coverage_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_actor_total=0,
        max_missing_trace_total=0,
        max_immutable_violation_total=0,
        min_snapshot_replay_ratio=0.95,
        min_diff_coverage_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert failures == []
