import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_gameday_drillpack.py"
    spec = importlib.util.spec_from_file_location("chat_gameday_drillpack", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_top_reasons_orders_by_count():
    module = _load_module()
    rows = [
        {"reason_code": "PROVIDER_TIMEOUT"},
        {"reason_code": "PROVIDER_TIMEOUT"},
        {"reason_code": "TOOL_FAIL"},
    ]
    top = module.summarize_top_reasons(rows, top_n=2)
    assert top[0]["reason_code"] == "PROVIDER_TIMEOUT"
    assert top[0]["count"] == 2
    assert top[1]["reason_code"] == "TOOL_FAIL"


def test_build_default_scenarios_contains_four_core_scenarios():
    module = _load_module()
    scenarios = module.build_default_scenarios([{"reason_code": "PROVIDER_TIMEOUT", "count": 3}])
    assert len(scenarios) == 4
    titles = [str(item["title"]) for item in scenarios]
    assert any("LLM timeout" in title for title in titles)
    assert any("Tool 장애" in title for title in titles)
    assert any("근거부족" in title for title in titles)
    assert any("비용/토큰" in title for title in titles)


def test_render_markdown_includes_checklist_sections():
    module = _load_module()
    payload = {
        "generated_at": "2026-03-03T00:00:00+00:00",
        "triage_file": "triage.jsonl",
        "triage_case_total": 2,
        "top_reasons": [{"reason_code": "PROVIDER_TIMEOUT", "count": 2}],
        "scenarios": module.build_default_scenarios([{"reason_code": "PROVIDER_TIMEOUT", "count": 2}]),
    }
    md = module.render_markdown(payload)
    assert "# Chat Gameday Drillpack" in md
    assert "## Scenarios" in md
    assert "- [ ]" in md


def test_compare_with_baseline_detects_triage_unknown_and_scenario_regression():
    module = _load_module()
    baseline = {
        "summary": {
            "triage_case_total": 1,
            "top_reasons": [{"reason_code": "UNKNOWN", "count": 0}],
            "scenario_total": 4,
        }
    }
    current = {
        "summary": {
            "triage_case_total": 20,
            "top_reasons": [{"reason_code": "UNKNOWN", "count": 10}],
            "scenario_total": 2,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_triage_case_increase=1,
        max_unknown_reason_increase=0,
        max_scenario_drop=0,
    )
    assert any("triage case regression" in item for item in failures)
    assert any("unknown reason regression" in item for item in failures)
    assert any("scenario coverage regression" in item for item in failures)
