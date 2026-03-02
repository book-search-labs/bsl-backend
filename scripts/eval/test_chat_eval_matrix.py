import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_eval_matrix.py"
    spec = importlib.util.spec_from_file_location("chat_eval_matrix", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_evaluate_gate_reads_aggregate_failures():
    module = _load_module()
    derived = {"aggregate_failures": ["contract_compat failures=1"]}
    failures = module.evaluate_gate(derived)
    assert failures == ["contract_compat failures=1"]


def test_compare_with_baseline_detects_gate_regression():
    module = _load_module()
    baseline = {"derived": {"gate_fail_total": 0}}
    current = {"gate_fail_total": 2}
    failures = module.compare_with_baseline(baseline, current, max_gate_fail_increase=1)
    assert len(failures) == 1
    assert "gate fail regression" in failures[0]
