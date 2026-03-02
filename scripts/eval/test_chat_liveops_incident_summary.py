import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_liveops_incident_summary.py"
    spec = importlib.util.spec_from_file_location("chat_liveops_incident_summary", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_incident_summary_resolves_single_incident(tmp_path: Path):
    module = _load_module()
    first = {
        "generated_at": "2026-03-02T12:00:00+00:00",
        "launch_gate": {"generated_at": "2026-03-02T11:59:30+00:00"},
        "release_train": {"decision": {"action": "rollback", "reason": "launch_gate_failed"}},
        "failures": ["x"],
    }
    second = {
        "generated_at": "2026-03-02T12:10:00+00:00",
        "launch_gate": {"generated_at": "2026-03-02T12:09:30+00:00"},
        "release_train": {"decision": {"action": "promote", "reason": "ok"}},
        "failures": [],
    }
    p1 = tmp_path / "chat_liveops_cycle_20260302_120000.json"
    p2 = tmp_path / "chat_liveops_cycle_20260302_121000.json"
    p1.write_text(json.dumps(first), encoding="utf-8")
    p2.write_text(json.dumps(second), encoding="utf-8")

    summary = module.build_incident_summary([p1, p2])
    assert summary["incident_total"] == 1
    assert summary["open_incident_total"] == 0
    assert summary["mtta_sec"] > 0.0
    assert summary["mttr_sec"] > 0.0


def test_evaluate_gate_detects_open_incidents():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "mtta_sec": 10.0,
            "mttr_sec": 20.0,
            "open_incident_total": 1,
        },
        min_window=3,
        max_mtta_sec=100.0,
        max_mttr_sec=100.0,
        max_open_incidents=0,
    )
    assert len(failures) == 1
    assert "open incidents exceeded" in failures[0]
