import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_contract_compat_eval.py"
    spec = importlib.util.spec_from_file_location("chat_contract_compat_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_resolve_path_supports_nested_objects_and_lists():
    module = _load_module()
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    exists, value = module._resolve_path(data, "a.b.1.c")
    assert exists is True
    assert value == 2


def test_validate_reason_code_pattern():
    module = _load_module()
    assert module._validate_reason_code("OK") is True
    assert module._validate_reason_code("TOOL_FAIL:SERVER_ERROR") is True
    assert module._validate_reason_code("bad_reason") is False
    assert module._validate_reason_code("") is False


def test_evaluate_gate_flags_failures():
    module = _load_module()
    derived = {
        "case_total": 2,
        "schema_fail_total": 1,
        "required_path_fail_total": 1,
        "reason_code_fail_total": 0,
    }
    failures = module.evaluate_gate(derived, min_cases=3, require_all=True)
    assert len(failures) == 3
    assert any("insufficient contract cases" in item for item in failures)
    assert any("schema compatibility failures" in item for item in failures)
    assert any("required path failures" in item for item in failures)


def test_compare_with_baseline_detects_regression():
    module = _load_module()
    baseline = {"derived": {"case_total": 5, "failures_total": 0}}
    current = {"case_total": 3, "failures_total": 2}
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_case_drop=1,
        max_failure_increase=0,
    )
    assert len(failures) == 2
    assert "case count regression" in failures[0]
    assert "compat failures regression" in failures[1]


def test_snapshot_path_types_tracks_nested_value_types():
    module = _load_module()
    snapshot = module._snapshot_path_types(
        {
            "status": "ok",
            "recoverable": False,
            "answer": {"content": "hello"},
            "sources": [{"citation_key": "policy#0"}],
        }
    )
    assert snapshot["$.status"] == "string"
    assert snapshot["$.recoverable"] == "boolean"
    assert snapshot["$.answer"] == "object"
    assert snapshot["$.answer.content"] == "string"
    assert snapshot["$.sources"] == "array"
    assert snapshot["$.sources.0.citation_key"] == "string"


def test_compare_with_baseline_detects_signature_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "case_total": 1,
            "failures_total": 0,
            "results": [
                {
                    "id": "chat_response_ok",
                    "schema": "contracts/chat-response.schema.json",
                    "signature": {
                        "schema": "contracts/chat-response.schema.json",
                        "path_types": {
                            "$": "object",
                            "$.status": "string",
                            "$.reason_code": "string",
                            "$.recoverable": "boolean",
                        },
                        "focus_fields": {
                            "reason_code": "OK",
                            "next_action": "NONE",
                            "recoverable": False,
                        },
                    },
                }
            ],
        }
    }
    current = {
        "case_total": 1,
        "failures_total": 0,
        "results": [
            {
                "id": "chat_response_ok",
                "schema": "contracts/chat-response.schema.json",
                "signature": {
                    "schema": "contracts/chat-response.schema.json",
                    "path_types": {
                        "$": "object",
                        "$.status": "string",
                        "$.recoverable": "string",
                    },
                    "focus_fields": {
                        "reason_code": "PROVIDER_TIMEOUT",
                        "next_action": "RETRY",
                        "recoverable": True,
                    },
                },
            }
        ],
    }

    failures = module.compare_with_baseline(
        baseline,
        current,
        max_case_drop=0,
        max_failure_increase=0,
    )

    assert any("removed paths" in item for item in failures)
    assert any("type changes" in item for item in failures)
    assert any("focus field changed: reason_code" in item for item in failures)
