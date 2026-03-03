import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_crosslingual_citation_parity_guard.py"
    spec = importlib.util.spec_from_file_location("chat_crosslingual_citation_parity_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_crosslingual_citation_parity_guard_tracks_mismatch_and_missing_citations():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "claim_id": "c1",
            "citation_id": "d1",
            "citation_parity_pass": True,
            "entailment_label": "entailed",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "claim_id": "c2",
            "citation_id": "d2",
            "citation_parity_pass": False,
            "entailment_label": "contradiction",
            "reason_code": "CITATION_PARITY_MISMATCH",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "claim_id": "c3",
            "citation_id": "",
            "citation_parity_pass": False,
            "entailment_label": "neutral",
            "reason_code": "",
        },
    ]
    summary = module.summarize_crosslingual_citation_parity_guard(
        rows,
        min_alignment_score=0.7,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["claim_total"] == 3
    assert summary["cited_claim_total"] == 2
    assert summary["citation_parity_pass_total"] == 1
    assert summary["citation_parity_ratio"] == 0.5
    assert summary["citation_mismatch_total"] == 2
    assert summary["missing_citation_total"] == 1
    assert summary["entailment_mismatch_total"] == 1
    assert summary["reason_code_missing_total"] == 1
    assert abs(summary["stale_minutes"] - (40.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_crosslingual_citation_parity_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "claim_total": 1,
            "citation_parity_ratio": 0.4,
            "citation_mismatch_total": 3,
            "missing_citation_total": 2,
            "entailment_mismatch_total": 2,
            "reason_code_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_claim_total=2,
        min_citation_parity_ratio=0.9,
        max_citation_mismatch_total=0,
        max_missing_citation_total=0,
        max_entailment_mismatch_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "claim_total": 0,
            "citation_parity_ratio": 1.0,
            "citation_mismatch_total": 0,
            "missing_citation_total": 0,
            "entailment_mismatch_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_claim_total=0,
        min_citation_parity_ratio=0.0,
        max_citation_mismatch_total=1000000,
        max_missing_citation_total=1000000,
        max_entailment_mismatch_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
