import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_answer_reliability_label.py"
    spec = importlib.util.spec_from_file_location("chat_answer_reliability_label", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_reliability_flags_low_level_violations():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "reliability_level": "LOW",
            "answer_text": "확정적으로 완료되었습니다.",
            "guidance_provided": False,
            "reason_code": "",
            "trust_score": 0.2,
            "stale_source_ratio": 0.8,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "reliability_level": "HIGH",
            "answer_text": "정책 기준으로 안내드립니다.",
            "guidance_provided": True,
            "reason_code": "ROUTE:ANSWER",
            "trust_score": 0.9,
            "stale_source_ratio": 0.0,
        },
    ]
    summary = module.summarize_reliability(rows, now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc))
    assert summary["answer_total"] == 2
    assert summary["low_total"] == 1
    assert summary["low_definitive_claim_total"] == 1
    assert summary["low_missing_guidance_total"] == 1
    assert summary["low_missing_reason_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "invalid_level_total": 1,
            "label_shift_ratio": 0.3,
            "low_definitive_claim_total": 2,
            "low_missing_guidance_total": 1,
            "low_missing_reason_total": 1,
            "low_guardrail_coverage_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_invalid_level_total=0,
        max_label_shift_ratio=0.1,
        max_low_definitive_claim_total=0,
        max_low_missing_guidance_total=0,
        max_low_missing_reason_total=0,
        min_low_guardrail_coverage_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "invalid_level_total": 0,
            "label_shift_ratio": 0.0,
            "low_definitive_claim_total": 0,
            "low_missing_guidance_total": 0,
            "low_missing_reason_total": 0,
            "low_guardrail_coverage_ratio": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_invalid_level_total=0,
        max_label_shift_ratio=0.1,
        max_low_definitive_claim_total=0,
        max_low_missing_guidance_total=0,
        max_low_missing_reason_total=0,
        min_low_guardrail_coverage_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert failures == []
