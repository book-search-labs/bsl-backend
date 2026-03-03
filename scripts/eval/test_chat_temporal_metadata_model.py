import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_temporal_metadata_model.py"
    spec = importlib.util.spec_from_file_location("chat_temporal_metadata_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_temporal_metadata_tracks_required_fields_and_overlap():
    module = _load_module()
    rows = [
        {
            "updated_at": "2026-03-03T00:00:00Z",
            "source_id": "p1",
            "effective_from": "2026-03-01T00:00:00Z",
            "effective_to": "2026-03-10T00:00:00Z",
            "announced_at": "2026-02-25T00:00:00Z",
            "timezone": "Asia/Seoul",
        },
        {
            "updated_at": "2026-03-03T00:01:00Z",
            "source_id": "p1",
            "effective_from": "2026-03-05T00:00:00Z",
            "effective_to": "2026-03-12T00:00:00Z",
            "announced_at": "2026-03-01T00:00:00Z",
            "timezone": "Asia/Seoul",
        },
        {
            "updated_at": "2026-03-03T00:02:00Z",
            "source_id": "",
            "effective_from": None,
            "effective_to": "2026-03-02T00:00:00Z",
            "announced_at": None,
            "timezone": "",
        },
        {
            "updated_at": "2026-03-03T00:03:00Z",
            "source_id": "p2",
            "effective_from": "2026-03-10T00:00:00Z",
            "effective_to": "2026-03-05T00:00:00Z",
            "announced_at": "2026-03-04T00:00:00Z",
            "timezone": "UTC",
        },
    ]
    summary = module.summarize_temporal_metadata(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["doc_total"] == 4
    assert summary["missing_source_id_total"] == 1
    assert summary["missing_effective_from_total"] == 1
    assert summary["missing_announced_at_total"] == 1
    assert summary["missing_timezone_total"] == 1
    assert summary["invalid_window_total"] == 1
    assert summary["open_ended_total"] == 0
    assert summary["overlap_conflict_total"] == 1
    assert summary["stale_hours"] == (1.0 / 60.0)


def test_evaluate_gate_detects_temporal_metadata_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "doc_total": 1,
            "missing_source_id_total": 1,
            "missing_effective_from_total": 1,
            "missing_announced_at_total": 1,
            "missing_timezone_total": 1,
            "invalid_window_total": 1,
            "overlap_conflict_total": 1,
            "stale_hours": 48.0,
        },
        min_window=10,
        min_doc_total=2,
        max_missing_source_id_total=0,
        max_missing_effective_from_total=0,
        max_missing_announced_at_total=0,
        max_missing_timezone_total=0,
        max_invalid_window_total=0,
        max_overlap_conflict_total=0,
        max_stale_hours=24.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "doc_total": 0,
            "missing_source_id_total": 0,
            "missing_effective_from_total": 0,
            "missing_announced_at_total": 0,
            "missing_timezone_total": 0,
            "invalid_window_total": 0,
            "overlap_conflict_total": 0,
            "stale_hours": 0.0,
        },
        min_window=0,
        min_doc_total=0,
        max_missing_source_id_total=1000000,
        max_missing_effective_from_total=1000000,
        max_missing_announced_at_total=1000000,
        max_missing_timezone_total=1000000,
        max_invalid_window_total=1000000,
        max_overlap_conflict_total=1000000,
        max_stale_hours=1000000.0,
    )
    assert failures == []
