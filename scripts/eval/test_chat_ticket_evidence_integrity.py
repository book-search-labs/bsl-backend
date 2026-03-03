import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_evidence_integrity.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_evidence_integrity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_evidence_integrity_tracks_links_and_versions():
    module = _load_module()
    rows = [
        {
            "ticket_id": "t1",
            "timestamp": "2026-03-03T00:00:00Z",
            "evidence_links": [{"url": "https://example.com/policy/1", "status": "OK"}],
            "policy_version": "policy-v1",
            "tool_version": "tool-v1",
            "evidence_hash": "hash-1",
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:01:00Z",
            "evidence_links": [],
            "policy_version": "",
            "tool_version": "",
            "evidence_hash": "",
        },
        {
            "ticket_id": "t3",
            "timestamp": "2026-03-03T00:02:00Z",
            "evidence_links": [
                {"url": "ht!tp://bad", "status": "BROKEN"},
                {"url": "https://example.com/a", "reachable": False},
            ],
            "policy_version": "policy-v1",
            "executed_tools": [{"name": "refund.check"}],
            "evidence_hash": "hash-3",
        },
    ]
    summary = module.summarize_evidence_integrity(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["pack_total"] == 3
    assert summary["missing_link_total"] == 1
    assert summary["invalid_url_total"] == 1
    assert summary["unresolved_link_total"] == 2
    assert summary["missing_policy_version_total"] == 1
    assert summary["missing_tool_version_total"] == 2
    assert summary["missing_evidence_hash_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_evidence_integrity_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "missing_link_total": 2,
            "invalid_url_total": 1,
            "unresolved_link_total": 1,
            "missing_policy_version_total": 1,
            "missing_tool_version_total": 1,
            "missing_evidence_hash_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_missing_link_total=0,
        max_invalid_url_total=0,
        max_unresolved_link_total=0,
        max_missing_policy_version_total=0,
        max_missing_tool_version_total=0,
        max_missing_evidence_hash_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_link_total": 0,
            "invalid_url_total": 0,
            "unresolved_link_total": 0,
            "missing_policy_version_total": 0,
            "missing_tool_version_total": 0,
            "missing_evidence_hash_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_link_total=1000000,
        max_invalid_url_total=1000000,
        max_unresolved_link_total=1000000,
        max_missing_policy_version_total=1000000,
        max_missing_tool_version_total=1000000,
        max_missing_evidence_hash_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
