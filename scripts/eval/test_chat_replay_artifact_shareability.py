import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_replay_artifact_shareability.py"
    spec = importlib.util.spec_from_file_location("chat_replay_artifact_shareability", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_artifact_shareability_tracks_redaction_and_scope():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "artifact_created": True,
            "shareable": True,
            "redaction_applied": True,
            "ticket_id": "RCA-1",
            "share_scope": "INTERNAL",
            "summary": "masked contact info",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "status": "CREATED",
            "artifact_path": "/tmp/replay-2.json",
            "share_url": "https://internal.example/replay-2",
            "summary": "user phone 010-1234-5678",
            "share_scope": "PUBLIC",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "status": "FAILED",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "status": "UPLOADED",
            "bundle_path": "/tmp/replay-3.bundle",
            "ticket_ref": "RCA-3",
            "redaction": {"applied": True},
            "share_scope": "RESTRICTED",
        },
    ]
    summary = module.summarize_artifact_shareability(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["artifact_created_total"] == 3
    assert summary["shareable_total"] == 3
    assert summary["redaction_applied_total"] == 2
    assert summary["missing_redaction_total"] == 1
    assert summary["unmasked_sensitive_total"] == 1
    assert summary["missing_ticket_reference_total"] == 1
    assert summary["invalid_share_scope_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_artifact_shareability_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "artifact_created_total": 1,
            "shareable_total": 0,
            "missing_redaction_total": 2,
            "unmasked_sensitive_total": 1,
            "missing_ticket_reference_total": 2,
            "invalid_share_scope_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_artifact_created_total=2,
        min_shareable_total=1,
        max_missing_redaction_total=0,
        max_unmasked_sensitive_total=0,
        max_missing_ticket_reference_total=0,
        max_invalid_share_scope_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "artifact_created_total": 0,
            "shareable_total": 0,
            "missing_redaction_total": 0,
            "unmasked_sensitive_total": 0,
            "missing_ticket_reference_total": 0,
            "invalid_share_scope_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_artifact_created_total=0,
        min_shareable_total=0,
        max_missing_redaction_total=1000000,
        max_unmasked_sensitive_total=1000000,
        max_missing_ticket_reference_total=1000000,
        max_invalid_share_scope_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_artifact_shareability_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "artifact_created_total": 20,
            "shareable_total": 20,
            "redaction_applied_total": 20,
            "missing_redaction_total": 0,
            "unmasked_sensitive_total": 0,
            "missing_ticket_reference_total": 0,
            "invalid_share_scope_total": 0,
            "redaction_ratio": 1.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "artifact_created_total": 1,
            "shareable_total": 1,
            "redaction_applied_total": 1,
            "missing_redaction_total": 1,
            "unmasked_sensitive_total": 1,
            "missing_ticket_reference_total": 1,
            "invalid_share_scope_total": 1,
            "redaction_ratio": 0.1,
            "stale_minutes": 80.0,
        },
        max_artifact_created_total_drop=1,
        max_shareable_total_drop=1,
        max_redaction_applied_total_drop=1,
        max_missing_redaction_total_increase=0,
        max_unmasked_sensitive_total_increase=0,
        max_missing_ticket_reference_total_increase=0,
        max_invalid_share_scope_total_increase=0,
        max_redaction_ratio_drop=0.05,
        max_stale_minutes_increase=30.0,
    )
    assert any("artifact_created_total regression" in item for item in failures)
    assert any("shareable_total regression" in item for item in failures)
    assert any("redaction_applied_total regression" in item for item in failures)
    assert any("missing_redaction_total regression" in item for item in failures)
    assert any("unmasked_sensitive_total regression" in item for item in failures)
    assert any("missing_ticket_reference_total regression" in item for item in failures)
    assert any("invalid_share_scope_total regression" in item for item in failures)
    assert any("redaction_ratio regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
