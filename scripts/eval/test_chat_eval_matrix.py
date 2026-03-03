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
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_gate_fail_increase=1,
        max_parity_mismatch_ratio_increase=0.1,
        max_parity_blocker_ratio_increase=0.1,
        require_baseline_approval=False,
        max_baseline_age_days=0,
    )
    assert len(failures) == 1
    assert "gate fail regression" in failures[0]


def test_compare_with_baseline_detects_critical_gate_pass_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "gate_fail_total": 0,
            "matrix": [
                {"gate": "contract_compat", "pass": True},
                {"gate": "reason_taxonomy", "pass": True},
                {"gate": "parity", "pass": True},
            ],
            "parity": {"derived": {"mismatch_ratio": 0.01, "blocker_ratio": 0.0}},
        }
    }
    current = {
        "gate_fail_total": 0,
        "matrix": [
            {"gate": "contract_compat", "pass": True},
            {"gate": "reason_taxonomy", "pass": True},
            {"gate": "parity", "pass": False},
        ],
        "parity": {"derived": {"mismatch_ratio": 0.05, "blocker_ratio": 0.0}},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_gate_fail_increase=0,
        max_parity_mismatch_ratio_increase=0.01,
        max_parity_blocker_ratio_increase=0.1,
        require_baseline_approval=False,
        max_baseline_age_days=0,
    )
    assert any("critical gate regression: gate=parity" in item for item in failures)
    assert any("parity mismatch ratio regression" in item for item in failures)


def test_compare_with_baseline_requires_approval_metadata_when_enabled():
    module = _load_module()
    baseline = {"generated_at": "2026-01-01T00:00:00+00:00", "derived": {"gate_fail_total": 0}}
    current = {"gate_fail_total": 0}
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_gate_fail_increase=0,
        max_parity_mismatch_ratio_increase=1.0,
        max_parity_blocker_ratio_increase=1.0,
        require_baseline_approval=True,
        max_baseline_age_days=0,
    )
    assert any("baseline metadata missing approved_by" in item for item in failures)
    assert any("baseline metadata missing approved_at" in item for item in failures)
    assert any("baseline metadata missing evidence" in item for item in failures)
