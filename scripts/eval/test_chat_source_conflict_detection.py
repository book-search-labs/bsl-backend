import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_source_conflict_detection.py"
    spec = importlib.util.spec_from_file_location("chat_source_conflict_detection", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_conflict_detection_tracks_severity_and_evidence():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "is_conflict": True,
            "conflict_severity": "HIGH",
            "conflict_type": "DATE",
            "topic_key": "REFUND_POLICY",
            "sources": ["official", "notice"],
            "evidence": [{"id": "ev1"}],
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "is_conflict": True,
            "conflict_severity": "BAD",
            "conflict_type": "",
            "topic_key": "",
            "sources": ["only-one"],
            "evidence": [],
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "is_conflict": False,
            "conflict_score": 0.0,
        },
    ]
    summary = module.summarize_conflict_detection(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["conflict_detected_total"] == 2
    assert summary["high_conflict_total"] == 1
    assert summary["invalid_severity_total"] == 1
    assert summary["missing_topic_total"] == 1
    assert summary["missing_conflict_type_total"] == 1
    assert summary["missing_source_pair_total"] == 1
    assert summary["missing_evidence_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_conflict_detection_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "conflict_detected_total": 2,
            "invalid_severity_total": 1,
            "missing_topic_total": 1,
            "missing_conflict_type_total": 1,
            "missing_source_pair_total": 1,
            "missing_evidence_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_conflict_detected_total=3,
        max_invalid_severity_total=0,
        max_missing_topic_total=0,
        max_missing_conflict_type_total=0,
        max_missing_source_pair_total=0,
        max_missing_evidence_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "conflict_detected_total": 0,
            "invalid_severity_total": 0,
            "missing_topic_total": 0,
            "missing_conflict_type_total": 0,
            "missing_source_pair_total": 0,
            "missing_evidence_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_conflict_detected_total=0,
        max_invalid_severity_total=1000000,
        max_missing_topic_total=1000000,
        max_missing_conflict_type_total=1000000,
        max_missing_source_pair_total=1000000,
        max_missing_evidence_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
