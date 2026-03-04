import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_temporal_answer_rendering.py"
    spec = importlib.util.spec_from_file_location("chat_temporal_answer_rendering", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_temporal_answer_rendering_tracks_render_contract_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "has_effective_date": True,
            "policy_version": "v1",
            "reference_date": "2026-03-03",
            "time_ambiguous": False,
            "has_official_source_link": True,
            "render_latency_ms": 120,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "answer_text": "정책 적용일은 2026-03-01이며 version v2 policy 입니다.",
            "has_reference_date": False,
            "ambiguous_query": True,
            "followup_asked": False,
            "source_links": [],
            "render_latency_ms": 400,
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "has_effective_date": True,
            "has_policy_version": True,
            "reference_time": "2026-03-03T00:03:00Z",
            "time_ambiguous": True,
            "route": "ASK",
            "citations": ["https://policy.book-search-labs.example/notice/1"],
            "render_latency_ms": 800,
        },
    ]
    summary = module.summarize_temporal_answer_rendering(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["answer_total"] == 3
    assert summary["with_effective_date_total"] == 3
    assert summary["with_policy_version_total"] == 3
    assert summary["missing_reference_date_total"] == 1
    assert summary["ambiguous_query_total"] == 2
    assert summary["ambiguous_followup_total"] == 1
    assert summary["ambiguous_direct_answer_total"] == 1
    assert summary["missing_official_source_link_total"] == 1
    assert summary["render_contract_violation_total"] == 1
    assert summary["p95_render_latency_ms"] == 800
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_temporal_answer_rendering_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "answer_total": 1,
            "effective_date_ratio": 0.5,
            "policy_version_ratio": 0.4,
            "ambiguous_followup_ratio": 0.3,
            "missing_reference_date_total": 2,
            "ambiguous_direct_answer_total": 1,
            "missing_official_source_link_total": 3,
            "render_contract_violation_total": 2,
            "p95_render_latency_ms": 5000.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_answer_total=2,
        min_effective_date_ratio=0.9,
        min_policy_version_ratio=0.9,
        min_ambiguous_followup_ratio=0.9,
        max_missing_reference_date_total=0,
        max_ambiguous_direct_answer_total=0,
        max_missing_official_source_link_total=0,
        max_render_contract_violation_total=0,
        max_p95_render_latency_ms=1000.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 11


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "answer_total": 0,
            "effective_date_ratio": 1.0,
            "policy_version_ratio": 1.0,
            "ambiguous_followup_ratio": 1.0,
            "missing_reference_date_total": 0,
            "ambiguous_direct_answer_total": 0,
            "missing_official_source_link_total": 0,
            "render_contract_violation_total": 0,
            "p95_render_latency_ms": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_answer_total=0,
        min_effective_date_ratio=0.0,
        min_policy_version_ratio=0.0,
        min_ambiguous_followup_ratio=0.0,
        max_missing_reference_date_total=1000000,
        max_ambiguous_direct_answer_total=1000000,
        max_missing_official_source_link_total=1000000,
        max_render_contract_violation_total=1000000,
        max_p95_render_latency_ms=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_temporal_answer_rendering_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "answer_total": 30,
            "with_effective_date_total": 30,
            "with_policy_version_total": 30,
            "effective_date_ratio": 1.0,
            "policy_version_ratio": 1.0,
            "ambiguous_followup_ratio": 1.0,
            "missing_reference_date_total": 0,
            "ambiguous_direct_answer_total": 0,
            "missing_official_source_link_total": 0,
            "render_contract_violation_total": 0,
            "p95_render_latency_ms": 120.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "answer_total": 1,
            "with_effective_date_total": 1,
            "with_policy_version_total": 1,
            "effective_date_ratio": 0.1,
            "policy_version_ratio": 0.1,
            "ambiguous_followup_ratio": 0.1,
            "missing_reference_date_total": 2,
            "ambiguous_direct_answer_total": 2,
            "missing_official_source_link_total": 2,
            "render_contract_violation_total": 2,
            "p95_render_latency_ms": 600.0,
            "stale_minutes": 80.0,
        },
        max_answer_total_drop=1,
        max_with_effective_date_total_drop=1,
        max_with_policy_version_total_drop=1,
        max_effective_date_ratio_drop=0.05,
        max_policy_version_ratio_drop=0.05,
        max_ambiguous_followup_ratio_drop=0.05,
        max_missing_reference_date_total_increase=0,
        max_ambiguous_direct_answer_total_increase=0,
        max_missing_official_source_link_total_increase=0,
        max_render_contract_violation_total_increase=0,
        max_p95_render_latency_ms_increase=100.0,
        max_stale_minutes_increase=30.0,
    )
    assert any("answer_total regression" in item for item in failures)
    assert any("with_effective_date_total regression" in item for item in failures)
    assert any("with_policy_version_total regression" in item for item in failures)
    assert any("effective_date_ratio regression" in item for item in failures)
    assert any("policy_version_ratio regression" in item for item in failures)
    assert any("ambiguous_followup_ratio regression" in item for item in failures)
    assert any("missing_reference_date_total regression" in item for item in failures)
    assert any("ambiguous_direct_answer_total regression" in item for item in failures)
    assert any("missing_official_source_link_total regression" in item for item in failures)
    assert any("render_contract_violation_total regression" in item for item in failures)
    assert any("p95_render_latency_ms regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
