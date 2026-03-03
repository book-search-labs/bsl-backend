import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_claim_verifier_guard.py"
    spec = importlib.util.spec_from_file_location("chat_claim_verifier_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_claim_verifier_guard_tracks_mismatch_and_mitigation():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "claim_id": "c1",
            "verdict": "SUPPORTED",
            "evidence_refs": ["d1#1"],
            "verifier_latency_ms": 100,
        },
        {
            "timestamp": "2026-03-03T00:00:05Z",
            "claim_id": "c2",
            "verdict": "MISMATCH",
            "evidence_refs": ["d2#3"],
            "claim_removed": True,
            "verifier_latency_ms": 400,
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "claim_id": "c3",
            "verdict": "UNSUPPORTED",
            "evidence_refs": [],
            "abstained": True,
            "verifier_latency_ms": 900,
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "claim_id": "c4",
            "claim_verified": False,
        },
    ]

    summary = module.summarize_claim_verifier_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["claim_total"] == 4
    assert summary["verified_claim_total"] == 3
    assert summary["verifier_coverage_ratio"] == 0.75
    assert summary["mismatch_total"] == 1
    assert abs(summary["mismatch_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["unsupported_total"] == 1
    assert summary["mismatch_mitigated_total"] == 1
    assert summary["mismatch_mitigated_ratio"] == 1.0
    assert summary["missing_evidence_ref_total"] == 1
    assert summary["p95_verifier_latency_ms"] == 900.0
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_claim_verifier_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "claim_total": 1,
            "verifier_coverage_ratio": 0.4,
            "mismatch_ratio": 0.6,
            "unsupported_total": 2,
            "mismatch_mitigated_ratio": 0.2,
            "missing_evidence_ref_total": 3,
            "p95_verifier_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_claim_total=2,
        min_verifier_coverage_ratio=0.95,
        max_mismatch_ratio=0.05,
        max_unsupported_total=0,
        min_mismatch_mitigated_ratio=0.99,
        max_missing_evidence_ref_total=0,
        max_p95_verifier_latency_ms=1500.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "claim_total": 0,
            "verifier_coverage_ratio": 1.0,
            "mismatch_ratio": 0.0,
            "unsupported_total": 0,
            "mismatch_mitigated_ratio": 1.0,
            "missing_evidence_ref_total": 0,
            "p95_verifier_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_claim_total=0,
        min_verifier_coverage_ratio=0.0,
        max_mismatch_ratio=1.0,
        max_unsupported_total=1000000,
        min_mismatch_mitigated_ratio=0.0,
        max_missing_evidence_ref_total=1000000,
        max_p95_verifier_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
