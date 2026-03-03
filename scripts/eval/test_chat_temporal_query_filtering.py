import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_temporal_query_filtering.py"
    spec = importlib.util.spec_from_file_location("chat_temporal_query_filtering", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_temporal_query_filtering_tracks_resolution_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "reference_type": "today",
            "reference_time": "2026-03-03T00:00:00Z",
            "reference_timezone": "Asia/Seoul",
            "matched_docs": [
                {"effective_from": "2026-03-01T00:00:00Z", "effective_to": "2026-03-10T00:00:00Z"}
            ],
            "resolve_latency_ms": 100,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "reference_type": "date",
            "reference_time": "2026-03-15T00:00:00Z",
            "matched_docs": [
                {"effective_from": "2026-03-01T00:00:00Z", "effective_to": "2026-03-10T00:00:00Z"}
            ],
            "reference_parse_error": True,
            "resolve_latency_ms": 300,
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "reference_type": "unknown",
            "reference_time": None,
            "matched_total": 0,
            "conflict_detected": True,
            "safe_abstention": False,
            "disambiguation_asked": False,
            "resolve_latency_ms": 500,
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "reference_type": "absolute",
            "reference_time": "2026-03-03T00:03:00Z",
            "matched_total": 0,
            "safe_abstention": True,
            "disambiguation_asked": True,
            "resolve_latency_ms": 900,
        },
    ]
    summary = module.summarize_temporal_query_filtering(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["request_total"] == 4
    assert summary["parse_error_total"] == 1
    assert summary["relative_reference_total"] == 1
    assert summary["explicit_reference_total"] == 2
    assert summary["missing_reference_time_total"] == 1
    assert summary["missing_reference_timezone_total"] == 3
    assert summary["matched_request_total"] == 2
    assert summary["zero_match_total"] == 2
    assert summary["invalid_match_request_total"] == 1
    assert summary["invalid_match_doc_total"] == 1
    assert summary["conflict_total"] == 1
    assert summary["conflict_unhandled_total"] == 1
    assert summary["disambiguation_total"] == 1
    assert summary["safe_abstention_total"] == 1
    assert summary["p95_resolve_latency_ms"] == 900
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_temporal_query_filtering_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "request_total": 1,
            "match_or_safe_ratio": 0.2,
            "parse_error_total": 2,
            "missing_reference_time_total": 1,
            "invalid_match_request_total": 1,
            "conflict_unhandled_total": 1,
            "p95_resolve_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_request_total=2,
        min_match_or_safe_ratio=0.9,
        max_parse_error_total=0,
        max_missing_reference_time_total=0,
        max_invalid_match_request_total=0,
        max_conflict_unhandled_total=0,
        max_p95_resolve_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "request_total": 0,
            "match_or_safe_ratio": 1.0,
            "parse_error_total": 0,
            "missing_reference_time_total": 0,
            "invalid_match_request_total": 0,
            "conflict_unhandled_total": 0,
            "p95_resolve_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_request_total=0,
        min_match_or_safe_ratio=0.0,
        max_parse_error_total=1000000,
        max_missing_reference_time_total=1000000,
        max_invalid_match_request_total=1000000,
        max_conflict_unhandled_total=1000000,
        max_p95_resolve_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
