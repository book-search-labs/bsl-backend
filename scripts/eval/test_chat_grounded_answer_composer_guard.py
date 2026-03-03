import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_grounded_answer_composer_guard.py"
    spec = importlib.util.spec_from_file_location("chat_grounded_answer_composer_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_grounded_answer_composer_guard_tracks_claim_binding():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "claims": [
                {"text": "c1", "evidence_ids": ["e1"], "included_in_output": True},
                {"text": "c2", "source_ids": ["s1"], "included_in_output": True},
            ],
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "claims": [
                {"text": "c3", "evidence_ids": ["e2"], "included_in_output": True},
                {"text": "c4", "included_in_output": False},
            ],
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "claims": [
                {"text": "c5", "included_in_output": True},
            ],
        },
    ]
    summary = module.summarize_grounded_answer_composer_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["response_total"] == 3
    assert summary["claim_total"] == 5
    assert summary["grounded_claim_total"] == 3
    assert summary["ungrounded_claim_total"] == 2
    assert abs(summary["claim_binding_coverage_ratio"] - 0.6) < 1e-9
    assert summary["response_with_ungrounded_total"] == 2
    assert summary["ungrounded_exposed_total"] == 1
    assert abs(summary["stale_minutes"] - (40.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_grounded_answer_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "response_total": 1,
            "claim_binding_coverage_ratio": 0.2,
            "response_with_ungrounded_total": 2,
            "ungrounded_exposed_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_response_total=2,
        min_claim_binding_coverage_ratio=0.95,
        max_response_with_ungrounded_total=0,
        max_ungrounded_exposed_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "response_total": 0,
            "claim_binding_coverage_ratio": 1.0,
            "response_with_ungrounded_total": 0,
            "ungrounded_exposed_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_response_total=0,
        min_claim_binding_coverage_ratio=0.0,
        max_response_with_ungrounded_total=1000000,
        max_ungrounded_exposed_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
