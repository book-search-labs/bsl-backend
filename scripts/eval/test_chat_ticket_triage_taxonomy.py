import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_triage_taxonomy.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_triage_taxonomy", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_triage_taxonomy_detects_missing_and_duplicates():
    module = _load_module()
    payload = {
        "version": "v1",
        "updated_at": "2026-03-03T00:00:00Z",
        "categories": [
            {"code": "ORDER", "severity_rules": ["S1", "S2", "S3"]},
            {"code": "PAYMENT", "severity_rules": ["S1", "S2"]},
            {"code": "PAYMENT", "severity_rules": ["S1"]},
            {"code": "SHIPPING"},
        ],
        "severities": ["S1", "S2", "S2"],
    }
    summary = module.summarize_triage_taxonomy(
        payload,
        required_categories={"ORDER", "PAYMENT", "SHIPPING", "REFUND", "ACCOUNT", "OTHER"},
        required_severities={"S1", "S2", "S3", "S4"},
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["category_total"] == 3
    assert summary["severity_total"] == 2
    assert summary["duplicate_category_total"] == 1
    assert summary["duplicate_severity_total"] == 1
    assert summary["missing_category_total"] == 3
    assert summary["missing_severity_total"] == 2
    assert summary["missing_severity_rule_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "category_total": 1,
            "severity_total": 1,
            "version_missing": True,
            "missing_category_total": 2,
            "missing_severity_total": 3,
            "duplicate_category_total": 1,
            "duplicate_severity_total": 1,
            "missing_severity_rule_total": 1,
            "stale_minutes": 120.0,
        },
        min_category_total=6,
        min_severity_total=4,
        require_taxonomy_version=True,
        max_missing_category_total=0,
        max_missing_severity_total=0,
        max_duplicate_category_total=0,
        max_duplicate_severity_total=0,
        max_missing_severity_rule_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_open_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "category_total": 0,
            "severity_total": 0,
            "version_missing": True,
            "missing_category_total": 0,
            "missing_severity_total": 0,
            "duplicate_category_total": 0,
            "duplicate_severity_total": 0,
            "missing_severity_rule_total": 0,
            "stale_minutes": 0.0,
        },
        min_category_total=0,
        min_severity_total=0,
        require_taxonomy_version=False,
        max_missing_category_total=1000000,
        max_missing_severity_total=1000000,
        max_duplicate_category_total=1000000,
        max_duplicate_severity_total=1000000,
        max_missing_severity_rule_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
