import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_knowledge_retrieval_impact_guard.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_knowledge_retrieval_impact_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_knowledge_retrieval_impact_guard_tracks_resolution_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "query_id": "q-1",
            "knowledge_hit": True,
            "resolved": True,
            "resolved_with_knowledge": True,
            "repeat_issue": True,
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "query_id": "q-2",
            "knowledge_hit": True,
            "resolved": False,
            "repeat_issue": True,
            "stale_knowledge_hit": True,
            "knowledge_conflict": True,
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "query_id": "q-3",
            "knowledge_hit": False,
            "resolved": True,
            "repeat_issue": False,
        },
        {
            "timestamp": "2026-03-03T00:00:40Z",
            "query_id": "q-4",
            "knowledge_hit": True,
            "resolved": True,
            "resolved_with_knowledge": True,
            "repeat_issue": True,
            "rollback_knowledge_hit": True,
        },
    ]

    summary = module.summarize_ticket_knowledge_retrieval_impact_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["query_total"] == 4
    assert summary["knowledge_hit_total"] == 3
    assert summary["knowledge_hit_ratio"] == 0.75
    assert summary["resolved_total"] == 3
    assert summary["resolved_with_knowledge_total"] == 2
    assert abs(summary["resolved_with_knowledge_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["repeat_issue_total"] == 3
    assert summary["repeat_issue_resolved_total"] == 2
    assert abs(summary["repeat_issue_resolution_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["stale_knowledge_hit_total"] == 1
    assert summary["rollback_knowledge_hit_total"] == 1
    assert summary["knowledge_conflict_total"] == 1
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_ticket_knowledge_retrieval_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "query_total": 1,
            "knowledge_hit_ratio": 0.2,
            "resolved_with_knowledge_ratio": 0.2,
            "repeat_issue_resolution_ratio": 0.1,
            "stale_knowledge_hit_total": 2,
            "rollback_knowledge_hit_total": 1,
            "knowledge_conflict_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_query_total=2,
        min_knowledge_hit_ratio=0.5,
        min_resolved_with_knowledge_ratio=0.6,
        min_repeat_issue_resolution_ratio=0.5,
        max_stale_knowledge_hit_total=0,
        max_rollback_knowledge_hit_total=0,
        max_knowledge_conflict_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "query_total": 0,
            "knowledge_hit_ratio": 1.0,
            "resolved_with_knowledge_ratio": 1.0,
            "repeat_issue_resolution_ratio": 1.0,
            "stale_knowledge_hit_total": 0,
            "rollback_knowledge_hit_total": 0,
            "knowledge_conflict_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_query_total=0,
        min_knowledge_hit_ratio=0.0,
        min_resolved_with_knowledge_ratio=0.0,
        min_repeat_issue_resolution_ratio=0.0,
        max_stale_knowledge_hit_total=1000000,
        max_rollback_knowledge_hit_total=1000000,
        max_knowledge_conflict_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
