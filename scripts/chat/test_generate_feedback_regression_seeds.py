import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "generate_feedback_regression_seeds.py"
    spec = importlib.util.spec_from_file_location("generate_feedback_regression_seeds", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_seed_payload_filters_by_reason_count():
    module = _load_module()
    records = [
        {"rating": "down", "reason_code": "AUTH_REQUIRED"},
        {"rating": "down", "reason_code": "AUTH_REQUIRED"},
        {"rating": "down", "reason_code": "MISSING_INPUT"},
        {"rating": "up", "reason_code": "AUTH_REQUIRED"},
    ]
    payload = module.build_seed_payload(records, min_reason_count=2, max_items=10)
    items = payload["items"]
    assert len(items) == 1
    assert items[0]["reason_code"] == "AUTH_REQUIRED"
    stub = items[0]["scenario_stub"]
    assert stub["turns"][0]["expected"]["reason_code"] == "AUTH_REQUIRED"


def test_scenario_stub_for_retryable_failure_contains_confirm_turns():
    module = _load_module()
    stub = module._scenario_stub_for_reason("TOOL_RETRYABLE_FAILURE")
    assert len(stub["turns"]) == 2
    assert stub["turns"][0]["expected"]["reason_code"] == "CONFIRMATION_REQUIRED"
    assert stub["turns"][1]["expected"]["reason_code"] == "TOOL_RETRYABLE_FAILURE"


def test_main_allow_empty_writes_outputs(tmp_path, monkeypatch):
    module = _load_module()
    input_path = tmp_path / "feedback.jsonl"
    output_json = tmp_path / "feedback_regression_seeds.json"
    output_md = tmp_path / "feedback_regression_seeds.md"
    input_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_feedback_regression_seeds.py",
            "--input",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--allow-empty",
        ],
    )
    assert module.main() == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["summary"]["total_records"] == 0
    assert payload["items"] == []
    assert "no seed candidates" in output_md.read_text(encoding="utf-8")


def test_main_without_allow_empty_fails_on_missing_records(tmp_path, monkeypatch):
    module = _load_module()
    input_path = tmp_path / "feedback.jsonl"
    output_json = tmp_path / "feedback_regression_seeds.json"
    output_md = tmp_path / "feedback_regression_seeds.md"
    input_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_feedback_regression_seeds.py",
            "--input",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )
    assert module.main() == 1
    assert not output_json.exists()
