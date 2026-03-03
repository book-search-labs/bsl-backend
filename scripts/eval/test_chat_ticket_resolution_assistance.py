import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_resolution_assistance.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_resolution_assistance", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_resolution_assistance_tracks_coverage_and_low_confidence():
    module = _load_module()
    rows = [
        {
            "ticket_id": "t1",
            "timestamp": "2026-03-03T00:00:00Z",
            "similar_cases": ["c1"],
            "resolution_templates": ["refund_template"],
            "suggested_questions": ["주문번호를 알려주세요."],
            "confidence": 0.90,
            "reason_code": "ASSIST_SIMILAR",
            "manual_review": False,
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:01:00Z",
            "similar_cases": [],
            "resolution_templates": ["delivery_template"],
            "suggested_questions": [],
            "confidence": 0.40,
            "reason_code": "",
            "manual_review": False,
        },
        {
            "ticket_id": "t3",
            "timestamp": "2026-03-03T00:02:00Z",
            "similar_cases": [],
            "resolution_templates": [],
            "suggested_questions": [],
            "confidence": 0.80,
            "reason_code": "ASSIST_NONE",
            "manual_review": False,
        },
    ]
    summary = module.summarize_resolution_assistance(
        rows,
        confidence_threshold=0.6,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["assistance_total"] == 3
    assert summary["with_similar_case_total"] == 1
    assert summary["with_template_total"] == 2
    assert summary["with_question_total"] == 1
    assert summary["similar_case_coverage_ratio"] == (1.0 / 3.0)
    assert summary["template_coverage_ratio"] == (2.0 / 3.0)
    assert summary["question_coverage_ratio"] == (1.0 / 3.0)
    assert summary["insufficient_assistance_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["low_confidence_unrouted_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_resolution_assistance_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "insufficient_assistance_total": 2,
            "similar_case_coverage_ratio": 0.1,
            "template_coverage_ratio": 0.2,
            "question_coverage_ratio": 0.3,
            "missing_reason_code_total": 2,
            "low_confidence_unrouted_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_insufficient_assistance_total=0,
        min_similar_case_coverage_ratio=0.5,
        min_template_coverage_ratio=0.6,
        min_question_coverage_ratio=0.7,
        max_missing_reason_code_total=0,
        max_low_confidence_unrouted_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "insufficient_assistance_total": 0,
            "similar_case_coverage_ratio": 1.0,
            "template_coverage_ratio": 1.0,
            "question_coverage_ratio": 1.0,
            "missing_reason_code_total": 0,
            "low_confidence_unrouted_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_insufficient_assistance_total=1000000,
        min_similar_case_coverage_ratio=0.0,
        min_template_coverage_ratio=0.0,
        min_question_coverage_ratio=0.0,
        max_missing_reason_code_total=1000000,
        max_low_confidence_unrouted_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
