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
