import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_rollout_eval.py"
    spec = importlib.util.spec_from_file_location("chat_rollout_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_parse_metric_key_with_labels():
    module = _load_module()
    name, labels = module.parse_metric_key("chat_rollout_gate_total{engine=agent,result=rollback}")
    assert name == "chat_rollout_gate_total"
    assert labels == {"engine": "agent", "result": "rollback"}


def test_collect_rollout_metrics_aggregates_gate_and_traffic():
    module = _load_module()
    snapshot = {
        "chat_rollout_traffic_ratio{engine=agent}": 8,
        "chat_rollout_traffic_ratio{engine=legacy}": 12,
        "chat_rollout_gate_total{engine=agent,result=pass}": 6,
        "chat_rollout_gate_total{engine=agent,result=rollback}": 2,
        "chat_rollout_failure_ratio{engine=agent}": 0.25,
        "chat_rollout_rollback_total{reason=gate_failure_ratio}": 1,
    }
    derived = module.collect_rollout_metrics(snapshot)
    assert derived["traffic"]["agent"] == 8
    assert derived["agent_gate"]["observed"] == 8
    assert derived["failure_ratio_agent"] == 0.25
    assert derived["rollback_total"] == 1


def test_evaluate_gate_flags_failures():
    module = _load_module()
    derived = {
        "failure_ratio_agent": 0.55,
        "rollback_total": 2,
        "agent_gate": {"observed": 9},
    }
    failures = module.evaluate_gate(
        derived,
        max_failure_ratio=0.2,
        max_rollback_total=0,
        require_min_samples=True,
        min_agent_samples=20,
        active_rollback=True,
        allow_active_rollback=False,
    )
    assert len(failures) == 4
    assert any("insufficient rollout gate sample" in item for item in failures)
    assert any("failure ratio too high" in item for item in failures)
    assert any("auto-rollback events exceed limit" in item for item in failures)
    assert any("active_rollback=true" in item for item in failures)


def test_compare_with_baseline_detects_regression():
    module = _load_module()
    baseline = {"derived": {"failure_ratio_agent": 0.1, "rollback_total": 0}}
    current = {"failure_ratio_agent": 0.25, "rollback_total": 1}
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_failure_ratio_increase=0.05,
        max_rollback_increase=0,
    )
    assert len(failures) == 2
    assert "failure ratio regression" in failures[0]
    assert "rollback total regression" in failures[1]
