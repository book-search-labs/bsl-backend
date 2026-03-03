import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_liveops_cycle.py"
    spec = importlib.util.spec_from_file_location("chat_liveops_cycle", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_parse_report_path_from_stdout():
    module = _load_module()
    output = "foo=bar\nreport_json=data/eval/reports/x.json\nreport_md=data/eval/reports/x.md\n"
    path = module._parse_report_path(output)
    assert path == "data/eval/reports/x.json"


def test_parse_report_path_returns_empty_when_missing():
    module = _load_module()
    assert module._parse_report_path("hello\nworld\n") == ""


def test_render_markdown_contains_action_and_signature():
    module = _load_module()
    report = {
        "generated_at": "2026-03-02T00:00:00+00:00",
        "release_profile": {"release_signature": "sig001"},
        "launch_gate": {"pass": True},
        "release_train": {"decision": {"action": "promote", "reason": "ok", "next_stage": 25}},
        "failures": [],
    }
    text = module.render_markdown(report)
    assert "release_signature: sig001" in text
    assert "release_action: promote" in text


def test_compare_with_baseline_detects_action_and_launch_regression():
    module = _load_module()
    baseline = {
        "failures": [],
        "launch_gate": {"pass": True},
        "release_train": {"decision": {"action": "promote"}},
    }
    current = {
        "runtime_failures": [],
        "launch_gate": {"pass": False},
        "release_train": {"decision": {"action": "rollback"}},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_cycle_failure_increase=0,
        max_cycle_action_drop=0,
    )
    assert any("launch gate pass regression" in item for item in failures)
    assert any("release action regression" in item for item in failures)


def test_compare_with_baseline_detects_failure_count_regression():
    module = _load_module()
    baseline = {"failures": ["a"], "launch_gate": {"pass": True}, "release_train": {"decision": {"action": "hold"}}}
    current = {"runtime_failures": ["a", "b", "c"], "launch_gate": {"pass": True}, "release_train": {"decision": {"action": "hold"}}}
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_cycle_failure_increase=1,
        max_cycle_action_drop=2,
    )
    assert len(failures) == 1
    assert "cycle failure regression" in failures[0]
