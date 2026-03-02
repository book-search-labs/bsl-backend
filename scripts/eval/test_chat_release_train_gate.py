import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_release_train_gate.py"
    spec = importlib.util.spec_from_file_location("chat_release_train_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_resolve_launch_gate_report_prefers_latest(tmp_path: Path):
    module = _load_module()
    r1 = tmp_path / "chat_production_launch_gate_20260302_100000.json"
    r2 = tmp_path / "chat_production_launch_gate_20260302_110000.json"
    r1.write_text("{}", encoding="utf-8")
    r2.write_text("{}", encoding="utf-8")
    resolved = module.resolve_launch_gate_report("", reports_dir=str(tmp_path), prefix="chat_production_launch_gate")
    assert resolved == r2


def test_decide_release_train_rolls_back_when_launch_gate_failed():
    module = _load_module()
    report = {
        "gate": {"pass": False},
        "derived": {
            "canary": {"passed": True, "reason": "within_threshold"},
            "perf": {"window_size": 100, "non_llm_p95_ms": 100, "llm_p95_ms": 100, "fallback_ratio": 0.0, "avg_tool_calls": 0.0},
        },
    }
    decision = module.decide_release_train(report, current_stage=25, dwell_minutes=60)
    assert decision["action"] == "rollback"
    assert decision["reason"] == "launch_gate_failed"


def test_decide_release_train_promotes_when_all_pass():
    module = _load_module()
    report = {
        "gate": {"pass": True},
        "derived": {
            "canary": {"passed": True, "reason": "within_threshold"},
            "perf": {
                "window_size": 100,
                "non_llm_count": 10,
                "llm_count": 10,
                "non_llm_p95_ms": 100,
                "llm_p95_ms": 500,
                "fallback_ratio": 0.0,
                "avg_tool_calls": 0.1,
            },
        },
    }
    decision = module.decide_release_train(report, current_stage=10, dwell_minutes=60)
    assert decision["action"] == "promote"
    assert decision["next_stage"] in {25, 50, 100}


def test_load_json_reads_payload(tmp_path: Path):
    module = _load_module()
    path = tmp_path / "report.json"
    payload = {"gate": {"pass": True}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = module.load_json(path)
    assert loaded["gate"]["pass"] is True
