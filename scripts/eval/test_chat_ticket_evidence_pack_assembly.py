import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_evidence_pack_assembly.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_evidence_pack_assembly", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_evidence_pack_assembly_tracks_coverage_latency_and_guidance():
    module = _load_module()
    ticket_rows = [
        {"ticket_id": "t1", "event_type": "TICKET_CREATED", "timestamp": "2026-03-03T00:00:00Z"},
        {"ticket_id": "t2", "event_type": "TICKET_CREATED", "timestamp": "2026-03-03T00:01:00Z"},
        {"ticket_id": "t3", "event_type": "TICKET_CREATED", "timestamp": "2026-03-03T00:02:00Z"},
    ]
    pack_rows = [
        {"ticket_id": "t1", "timestamp": "2026-03-03T00:00:30Z", "missing_fields": []},
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:03:00Z",
            "missing_fields": ["order_id"],
            "followup_prompt": "주문번호를 알려주세요.",
        },
        {"ticket_id": "t4", "timestamp": "2026-03-03T00:04:00Z", "missing_fields": ["intent"]},
    ]
    summary = module.summarize_evidence_pack_assembly(
        ticket_rows,
        pack_rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["ticket_created_total"] == 3
    assert summary["pack_total"] == 3
    assert summary["pack_assembled_total"] == 2
    assert summary["missing_pack_total"] == 1
    assert summary["pack_coverage_ratio"] == (2.0 / 3.0)
    assert summary["missing_field_total"] == 2
    assert summary["missing_field_guidance_missing_total"] == 1
    assert summary["latency_sample_total"] == 2
    assert summary["p95_assembly_latency_seconds"] == 120.0
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_evidence_pack_assembly_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "missing_pack_total": 2,
            "pack_coverage_ratio": 0.5,
            "missing_field_guidance_missing_total": 2,
            "p95_assembly_latency_seconds": 300.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_missing_pack_total=0,
        min_pack_coverage_ratio=0.9,
        max_missing_field_guidance_missing_total=0,
        max_p95_assembly_latency_seconds=120.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_pack_total": 0,
            "pack_coverage_ratio": 1.0,
            "missing_field_guidance_missing_total": 0,
            "p95_assembly_latency_seconds": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_pack_total=1000000,
        min_pack_coverage_ratio=0.0,
        max_missing_field_guidance_missing_total=1000000,
        max_p95_assembly_latency_seconds=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_evidence_pack_assembly_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "ticket_created_total": 20,
            "pack_assembled_total": 20,
            "missing_pack_total": 0,
            "pack_coverage_ratio": 1.0,
            "missing_field_total": 0,
            "missing_field_guidance_missing_total": 0,
            "p95_assembly_latency_seconds": 60.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "ticket_created_total": 1,
            "pack_assembled_total": 1,
            "missing_pack_total": 2,
            "pack_coverage_ratio": 0.3,
            "missing_field_total": 3,
            "missing_field_guidance_missing_total": 2,
            "p95_assembly_latency_seconds": 180.0,
            "stale_minutes": 80.0,
        },
        max_ticket_created_total_drop=1,
        max_pack_assembled_total_drop=1,
        max_missing_pack_total_increase=0,
        max_pack_coverage_ratio_drop=0.05,
        max_missing_field_total_increase=0,
        max_missing_field_guidance_missing_total_increase=0,
        max_p95_assembly_latency_seconds_increase=30.0,
        max_stale_minutes_increase=30.0,
    )
    assert any("ticket_created_total regression" in item for item in failures)
    assert any("pack_assembled_total regression" in item for item in failures)
    assert any("missing_pack_total regression" in item for item in failures)
    assert any("pack_coverage_ratio regression" in item for item in failures)
    assert any("missing_field_total regression" in item for item in failures)
    assert any("missing_field_guidance_missing_total regression" in item for item in failures)
    assert any("p95_assembly_latency_seconds regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
