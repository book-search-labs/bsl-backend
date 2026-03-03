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
