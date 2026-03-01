import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_regression_suite_eval.py"
    spec = importlib.util.spec_from_file_location("chat_regression_suite_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_classify_domain_prefers_book_patterns():
    module = _load_module()
    scenario = {
        "id": "S_book_followup",
        "turns": [
            {"query": "책 추천해줘"},
            {"query": "다른 출판사 추천해줘"},
        ],
    }
    assert module.classify_domain(scenario) == "book"


def test_collect_suite_metrics_counts_turns_and_domains():
    module = _load_module()
    suite = {
        "suite": "sample",
        "scenarios": [
            {"id": "S1", "turns": [{"query": "주문 상태"}, {"query": "확인"}]},
            {"id": "S2", "turns": [{"query": "문의 상태"}]},
            {"id": "S3", "turns": [{"query": "책 추천"}]},
        ],
    }
    derived = module.collect_suite_metrics(suite)
    assert derived["scenario_count"] == 3
    assert derived["turn_count"] == 4
    assert derived["multi_turn_scenario_count"] == 1
    assert derived["domain_counts"]["commerce"] == 1
    assert derived["domain_counts"]["support"] == 1
    assert derived["domain_counts"]["book"] == 1


def test_evaluate_gate_flags_missing_thresholds():
    module = _load_module()
    derived = {
        "scenario_count": 10,
        "turn_count": 12,
        "multi_turn_scenario_count": 2,
        "domain_counts": {"book": 1},
    }
    failures = module.evaluate_gate(
        derived,
        min_scenarios=30,
        min_turns=45,
        min_multi_turn_scenarios=12,
        min_book_scenarios=8,
        ingest_count=0,
        require_ingest=True,
        min_ingest_cases=1,
    )
    assert len(failures) == 5
    assert any("insufficient scenario count" in item for item in failures)
    assert any("insufficient turn count" in item for item in failures)
    assert any("insufficient multi-turn scenarios" in item for item in failures)
    assert any("insufficient book-domain scenarios" in item for item in failures)
    assert any("insufficient new-case ingestion" in item for item in failures)


def test_compare_with_baseline_detects_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "scenario_count": 40,
            "turn_count": 80,
            "domain_counts": {"book": 12},
        }
    }
    current = {
        "scenario_count": 36,
        "turn_count": 70,
        "domain_counts": {"book": 10},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_scenario_drop=2,
        max_turn_drop=5,
        max_book_drop=1,
    )
    assert len(failures) == 3
    assert "scenario count regression" in failures[0]
    assert "turn count regression" in failures[1]
    assert "book scenario regression" in failures[2]
