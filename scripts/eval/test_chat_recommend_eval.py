import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_recommend_eval.py"
    spec = importlib.util.spec_from_file_location("chat_recommend_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_parse_metric_key_with_labels():
    module = _load_module()
    name, labels = module.parse_metric_key("chat_recommend_experiment_total{status=served,variant=diversity}")
    assert name == "chat_recommend_experiment_total"
    assert labels == {"status": "served", "variant": "diversity"}


def test_collect_recommend_metrics_uses_gauge_block_rate():
    module = _load_module()
    snapshot = {
        "chat_recommend_experiment_total{variant=diversity,status=assigned}": 12,
        "chat_recommend_experiment_total{variant=diversity,status=served}": 7,
        "chat_recommend_experiment_total{variant=diversity,status=blocked}": 3,
        "chat_recommend_experiment_total{variant=baseline,status=served}": 9,
        "chat_recommend_experiment_auto_disable_total{reason=quality_block_rate}": 1,
        "chat_recommend_quality_gate_block_total{reason=low_diversity}": 3,
        "chat_recommend_experiment_block_rate{variant=diversity}": 0.25,
    }
    derived = module.collect_recommend_metrics(snapshot)
    diversity = derived["diversity"]
    assert diversity["assigned"] == 12
    assert diversity["served"] == 7
    assert diversity["blocked"] == 3
    assert diversity["observed"] == 10
    assert diversity["block_rate"] == 0.25
    assert diversity["block_rate_source"] == "gauge"
    assert derived["quality_blocks"]["low_diversity"] == 3
    assert derived["overall_auto_disable_total"] == 1


def test_evaluate_gate_flags_failures():
    module = _load_module()
    derived = {
        "overall_auto_disable_total": 2,
        "diversity": {
            "observed": 9,
            "block_rate": 0.55,
        },
    }
    failures = module.evaluate_gate(
        derived,
        min_samples=20,
        max_block_rate=0.4,
        max_auto_disable_total=0,
        require_min_samples=True,
        session_auto_disabled=True,
    )
    assert len(failures) == 4
    assert any("insufficient diversity sample" in item for item in failures)
    assert any("quality block rate too high" in item for item in failures)
    assert any("auto-disable events exceed limit" in item for item in failures)
    assert any("auto_disabled=true" in item for item in failures)


def test_compare_with_baseline_detects_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "overall_auto_disable_total": 0,
            "diversity": {"block_rate": 0.2},
        }
    }
    current = {
        "overall_auto_disable_total": 1,
        "diversity": {"block_rate": 0.31},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_block_rate_increase=0.05,
        max_auto_disable_increase=0,
    )
    assert len(failures) == 2
    assert "block rate regression" in failures[0]
    assert "auto-disable regression" in failures[1]
