import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_cutover_gate.py"
    spec = importlib.util.spec_from_file_location("chat_cutover_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_evaluate_gate_passes_when_parity_perf_ok_and_hold_allowed():
    module = _load_module()
    derived = {
        "parity_gate": {"passed": True, "reason": "within_threshold"},
        "perf_gate": {"passed": True, "failures": []},
        "cutover": {"action": "hold", "reason": "dwell_not_met"},
    }
    failures = module.evaluate_gate(derived, require_promote=False)
    assert failures == []


def test_evaluate_gate_fails_on_rollback_and_perf_failure():
    module = _load_module()
    derived = {
        "parity_gate": {"passed": False, "reason": "blocker_ratio_exceeded"},
        "perf_gate": {"passed": False, "failures": ["fallback ratio exceeded: 0.2 > 0.1"]},
        "cutover": {"action": "rollback", "reason": "budget_gate_failed"},
    }
    failures = module.evaluate_gate(derived, require_promote=False)
    assert any("parity gate failed" in item for item in failures)
    assert any("perf gate failed" in item for item in failures)
    assert any("cutover action=rollback" in item for item in failures)


def test_evaluate_gate_require_promote_blocks_hold():
    module = _load_module()
    derived = {
        "parity_gate": {"passed": True, "reason": "within_threshold"},
        "perf_gate": {"passed": True, "failures": []},
        "cutover": {"action": "hold", "reason": "dwell_not_met"},
    }
    failures = module.evaluate_gate(derived, require_promote=True)
    assert len(failures) == 1
    assert "cutover promote required but action=hold" in failures[0]
