import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_temporal_conflict_fallback.py"
    spec = importlib.util.spec_from_file_location("chat_temporal_conflict_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_temporal_conflict_fallback_tracks_safe_fallback_compliance():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "temporal_conflict": True,
            "requires_fallback": True,
            "decision": "ASK",
            "followup_asked": True,
            "source_links": ["https://policy.book-search-labs.example/r1"],
            "reason_code": "TEMPORAL_CONFLICT_DISAMBIGUATE",
            "fallback_latency_ms": 180,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "conflict_type": "effective_date",
            "resolution_status": "UNRESOLVED",
            "decision": "ANSWER",
            "definitive_claim": True,
            "assistant_message": "정책이 변경되었을 수 있습니다.",
            "source_links": [],
            "reason_code": "",
            "fallback_latency_ms": 420,
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "temporal_conflict": False,
            "decision": "ANSWER",
            "fallback_latency_ms": 100,
        },
    ]
    summary = module.summarize_temporal_conflict_fallback(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["temporal_conflict_total"] == 2
    assert summary["fallback_expected_total"] == 2
    assert summary["safe_fallback_total"] == 1
    assert summary["fallback_coverage_ratio"] == 0.5
    assert summary["unsafe_resolution_total"] == 1
    assert summary["missing_followup_prompt_total"] == 1
    assert summary["missing_official_source_link_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["p95_fallback_latency_ms"] == 420
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_temporal_conflict_fallback_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "temporal_conflict_total": 1,
            "fallback_coverage_ratio": 0.2,
            "unsafe_resolution_total": 2,
            "missing_followup_prompt_total": 2,
            "missing_official_source_link_total": 3,
            "missing_reason_code_total": 1,
            "p95_fallback_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_temporal_conflict_total=2,
        min_fallback_coverage_ratio=0.9,
        max_unsafe_resolution_total=0,
        max_missing_followup_prompt_total=0,
        max_missing_official_source_link_total=0,
        max_missing_reason_code_total=0,
        max_p95_fallback_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "temporal_conflict_total": 0,
            "fallback_coverage_ratio": 1.0,
            "unsafe_resolution_total": 0,
            "missing_followup_prompt_total": 0,
            "missing_official_source_link_total": 0,
            "missing_reason_code_total": 0,
            "p95_fallback_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_temporal_conflict_total=0,
        min_fallback_coverage_ratio=0.0,
        max_unsafe_resolution_total=1000000,
        max_missing_followup_prompt_total=1000000,
        max_missing_official_source_link_total=1000000,
        max_missing_reason_code_total=1000000,
        max_p95_fallback_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
