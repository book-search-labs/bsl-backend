import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_semantic_cache_eval.py"
    spec = importlib.util.spec_from_file_location("chat_semantic_cache_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_parse_metric_key_with_labels():
    module = _load_module()
    name, labels = module.parse_metric_key("chat_semantic_cache_block_total{reason=AUTO_DISABLED}")
    assert name == "chat_semantic_cache_block_total"
    assert labels == {"reason": "AUTO_DISABLED"}


def test_collect_semantic_cache_metrics_aggregates_values():
    module = _load_module()
    snapshot = {
        "chat_semantic_cache_quality_total{result=ok,reason=HIT}": 8,
        "chat_semantic_cache_quality_total{result=error,reason=BAD_STATUS}": 2,
        "chat_semantic_cache_hit_total{lane=policy,topic=refund}": 7,
        "chat_semantic_cache_store_total{lane=policy,topic=refund}": 4,
        "chat_semantic_cache_block_total{reason=SIMILARITY_THRESHOLD}": 3,
        "chat_semantic_cache_auto_disable_total{reason=drift}": 1,
    }
    derived = module.collect_semantic_cache_metrics(snapshot)
    assert derived["quality_total"] == 10
    assert derived["quality_error"] == 2
    assert derived["quality_error_rate"] == 0.2
    assert derived["hit_total"] == 7
    assert derived["block_total"] == 3
    assert derived["auto_disable_total"] == 1


def test_evaluate_gate_flags_failures():
    module = _load_module()
    derived = {
        "quality_total": 9,
        "quality_error_rate": 0.6,
        "auto_disable_total": 2,
    }
    failures = module.evaluate_gate(
        derived,
        min_quality_samples=20,
        max_error_rate=0.2,
        max_auto_disable_total=0,
        require_min_samples=True,
        session_auto_disabled=True,
    )
    assert len(failures) == 4
    assert any("insufficient semantic cache quality samples" in item for item in failures)
    assert any("semantic cache error rate too high" in item for item in failures)
    assert any("semantic cache auto-disable events exceed limit" in item for item in failures)
    assert any("session snapshot indicates semantic_cache auto_disabled=true" in item for item in failures)


def test_compare_with_baseline_detects_regression():
    module = _load_module()
    baseline = {"derived": {"quality_error_rate": 0.1, "auto_disable_total": 0}}
    current = {"quality_error_rate": 0.25, "auto_disable_total": 1}
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_error_rate_increase=0.05,
        max_auto_disable_increase=0,
    )
    assert len(failures) == 2
    assert "semantic cache error rate regression" in failures[0]
    assert "semantic cache auto-disable regression" in failures[1]
