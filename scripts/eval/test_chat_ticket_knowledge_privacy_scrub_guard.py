import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_knowledge_privacy_scrub_guard.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_knowledge_privacy_scrub_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_knowledge_privacy_scrub_guard_tracks_pii_leaks():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "candidate_generated": True,
            "pii_detected": True,
            "privacy_scrub_applied": True,
            "pii_after_scrub": False,
            "redaction_rule_version": "v1",
            "retention_policy_applied": True,
            "message_storage_mode": "masked_raw",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "candidate_generated": True,
            "pii_types": ["phone"],
            "privacy_scrub_applied": True,
            "pii_after_scrub": True,
            "redaction_rule_version": "",
            "retention_policy_applied": False,
            "message_storage_mode": "raw_full",
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "candidate_generated": True,
            "pii_detected": False,
            "privacy_scrub_applied": False,
            "retention_policy_applied": True,
            "message_storage_mode": "hash_summary",
        },
    ]

    summary = module.summarize_ticket_knowledge_privacy_scrub_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["candidate_total"] == 3
    assert summary["scrubbed_total"] == 2
    assert abs(summary["scrub_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["pii_detected_total"] == 2
    assert summary["pii_leak_total"] == 1
    assert summary["redaction_rule_missing_total"] == 1
    assert summary["retention_policy_missing_total"] == 1
    assert summary["unsafe_storage_mode_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_ticket_knowledge_privacy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "candidate_total": 1,
            "scrub_coverage_ratio": 0.2,
            "pii_leak_total": 2,
            "redaction_rule_missing_total": 1,
            "retention_policy_missing_total": 1,
            "unsafe_storage_mode_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_candidate_total=2,
        min_scrub_coverage_ratio=0.95,
        max_pii_leak_total=0,
        max_redaction_rule_missing_total=0,
        max_retention_policy_missing_total=0,
        max_unsafe_storage_mode_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "candidate_total": 0,
            "scrub_coverage_ratio": 1.0,
            "pii_leak_total": 0,
            "redaction_rule_missing_total": 0,
            "retention_policy_missing_total": 0,
            "unsafe_storage_mode_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_candidate_total=0,
        min_scrub_coverage_ratio=0.0,
        max_pii_leak_total=1000000,
        max_redaction_rule_missing_total=1000000,
        max_retention_policy_missing_total=1000000,
        max_unsafe_storage_mode_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
