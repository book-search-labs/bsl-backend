import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_knowledge_candidate_selection.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_knowledge_candidate_selection", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_knowledge_candidate_selection_tracks_invalid_candidates():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "ticket_status": "closed",
            "candidate_generated": True,
            "candidate_score": 0.91,
            "issue_type": "refund_policy",
            "resolution_pattern": "policy_guided_resolution",
            "ticket_id": "T-100",
            "closed_at": "2026-03-03T00:00:00Z",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "ticket_status": "open",
            "candidate_generated": True,
            "candidate_score": 0.30,
            "issue_type": "",
            "resolution_pattern": "",
            "ticket_id": "",
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "ticket_status": "resolved",
            "candidate_generated": False,
        },
    ]

    summary = module.summarize_ticket_knowledge_candidate_selection(
        rows,
        min_reusable_score=0.6,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["ticket_total"] == 3
    assert summary["closed_ticket_total"] == 2
    assert summary["candidate_total"] == 2
    assert summary["candidate_rate"] == 1.0
    assert summary["invalid_status_candidate_total"] == 1
    assert summary["low_confidence_candidate_total"] == 1
    assert summary["candidate_taxonomy_missing_total"] == 1
    assert summary["source_provenance_missing_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_ticket_knowledge_candidate_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "ticket_total": 1,
            "closed_ticket_total": 0,
            "candidate_total": 0,
            "candidate_rate": 0.2,
            "invalid_status_candidate_total": 2,
            "low_confidence_candidate_total": 1,
            "candidate_taxonomy_missing_total": 3,
            "source_provenance_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_ticket_total=2,
        min_closed_ticket_total=1,
        min_candidate_total=1,
        min_candidate_rate=0.5,
        max_invalid_status_candidate_total=0,
        max_low_confidence_candidate_total=0,
        max_candidate_taxonomy_missing_total=0,
        max_source_provenance_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "ticket_total": 0,
            "closed_ticket_total": 0,
            "candidate_total": 0,
            "candidate_rate": 1.0,
            "invalid_status_candidate_total": 0,
            "low_confidence_candidate_total": 0,
            "candidate_taxonomy_missing_total": 0,
            "source_provenance_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_ticket_total=0,
        min_closed_ticket_total=0,
        min_candidate_total=0,
        min_candidate_rate=0.0,
        max_invalid_status_candidate_total=1000000,
        max_low_confidence_candidate_total=1000000,
        max_candidate_taxonomy_missing_total=1000000,
        max_source_provenance_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
