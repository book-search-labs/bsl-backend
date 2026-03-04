import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_privacy_dlp_filter.py"
    spec = importlib.util.spec_from_file_location("chat_privacy_dlp_filter", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_dlp_filter_tracks_detection_and_protection():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "pii_types": ["EMAIL"],
            "action": "MASK",
            "reason_code": "PII:EMAIL",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "pii_type": "PHONE",
            "policy_action": "BLOCKED",
            "reason_code": "PII:PHONE",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "pii_detected": True,
            "pii_type": "ALIEN",
            "action": "ALLOW",
            "override_approved": False,
            "false_positive": True,
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "pii_type": "ADDRESS",
            "action": "MANUAL_REVIEW",
            "reason_code": "PII:ADDRESS",
        },
    ]
    summary = module.summarize_dlp_filter(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["detected_total"] == 4
    assert summary["masked_total"] == 1
    assert summary["blocked_total"] == 1
    assert summary["review_total"] == 1
    assert summary["allowed_total"] == 1
    assert summary["protected_action_ratio"] == 0.75
    assert summary["unmasked_violation_total"] == 1
    assert summary["false_positive_total"] == 1
    assert summary["invalid_action_total"] == 0
    assert summary["unknown_pii_type_total"] == 1
    assert summary["missing_reason_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_dlp_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "detected_total": 1,
            "protected_action_ratio": 0.2,
            "unmasked_violation_total": 2,
            "invalid_action_total": 1,
            "unknown_pii_type_total": 1,
            "false_positive_total": 2,
            "missing_reason_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_detected_total=2,
        min_protected_action_ratio=0.9,
        max_unmasked_violation_total=0,
        max_invalid_action_total=0,
        max_unknown_pii_type_total=0,
        max_false_positive_total=0,
        max_missing_reason_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimum_is_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "detected_total": 0,
            "protected_action_ratio": 1.0,
            "unmasked_violation_total": 0,
            "invalid_action_total": 0,
            "unknown_pii_type_total": 0,
            "false_positive_total": 0,
            "missing_reason_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_detected_total=0,
        min_protected_action_ratio=0.0,
        max_unmasked_violation_total=1000000,
        max_invalid_action_total=1000000,
        max_unknown_pii_type_total=1000000,
        max_false_positive_total=1000000,
        max_missing_reason_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_dlp_filter_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "detected_total": 20,
            "protected_action_ratio": 0.95,
            "unmasked_violation_total": 0,
            "invalid_action_total": 0,
            "unknown_pii_type_total": 0,
            "false_positive_total": 0,
            "missing_reason_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "detected_total": 1,
            "protected_action_ratio": 0.1,
            "unmasked_violation_total": 2,
            "invalid_action_total": 1,
            "unknown_pii_type_total": 1,
            "false_positive_total": 1,
            "missing_reason_total": 1,
            "stale_minutes": 80.0,
        },
        max_detected_total_drop=1,
        max_protected_action_ratio_drop=0.05,
        max_unmasked_violation_total_increase=0,
        max_invalid_action_total_increase=0,
        max_unknown_pii_type_total_increase=0,
        max_false_positive_total_increase=0,
        max_missing_reason_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("detected_total regression" in item for item in failures)
    assert any("protected_action_ratio regression" in item for item in failures)
    assert any("unmasked_violation_total regression" in item for item in failures)
    assert any("invalid_action_total regression" in item for item in failures)
    assert any("unknown_pii_type_total regression" in item for item in failures)
    assert any("false_positive_total regression" in item for item in failures)
    assert any("missing_reason_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
