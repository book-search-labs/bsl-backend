import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_reason_taxonomy_eval.py"
    spec = importlib.util.spec_from_file_location("chat_reason_taxonomy_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _assessor(reason_code, source):
    reason = str(reason_code or "")
    if reason in {"UNKNOWN", "bad_reason"}:
        return {"normalized_reason_code": "CHAT_REASON_CODE_INVALID", "invalid": True, "unknown": False}
    if source == "policy_decide" and reason == "PROVIDER_TIMEOUT":
        return {"normalized_reason_code": "PROVIDER_TIMEOUT", "invalid": False, "unknown": True}
    return {"normalized_reason_code": reason or "CHAT_REASON_UNSPECIFIED", "invalid": False, "unknown": False}


def test_evaluate_case_fixture_counts_mismatch():
    module = _load_module()
    payload = {
        "cases": [
            {"id": "ok", "source": "response", "reason_code": "OK", "expect": "valid"},
            {"id": "unknown", "source": "policy_decide", "reason_code": "PROVIDER_TIMEOUT", "expect": "unknown"},
            {"id": "invalid", "source": "response", "reason_code": "UNKNOWN", "expect": "invalid"},
            {"id": "mismatch", "source": "response", "reason_code": "OK", "expect": "invalid"},
        ]
    }
    derived = module.evaluate_case_fixture(payload, assessor=_assessor)
    assert derived["case_total"] == 4
    assert derived["invalid_total"] == 1
    assert derived["unknown_total"] == 1
    assert derived["mismatch_total"] == 1


def test_evaluate_response_fixture_counts_invalid_unknown():
    module = _load_module()
    payload = {
        "responses": [
            {"id": "a", "source": "response", "response": {"status": "ok", "reason_code": "OK"}},
            {"id": "b", "source": "response", "response": {"status": "insufficient_evidence", "reason_code": "UNKNOWN"}},
            {
                "id": "c",
                "source": "policy_decide",
                "response": {"status": "insufficient_evidence", "reason_code": "PROVIDER_TIMEOUT"},
            },
        ]
    }
    derived = module.evaluate_response_fixture(payload, assessor=_assessor)
    assert derived["response_total"] == 3
    assert derived["invalid_total"] == 1
    assert derived["unknown_total"] == 1


def test_evaluate_gate_and_baseline_compare():
    module = _load_module()
    derived = {
        "case_total": 5,
        "response_total": 3,
        "mismatch_total": 0,
        "invalid_ratio": 0.0,
        "unknown_ratio": 0.02,
    }
    failures = module.evaluate_gate(
        derived,
        min_cases=5,
        min_response_total=1,
        max_invalid_ratio=0.0,
        max_unknown_ratio=0.03,
    )
    assert failures == []

    baseline = {"derived": {"invalid_ratio": 0.0, "unknown_ratio": 0.0}}
    regressions = module.compare_with_baseline(
        baseline,
        derived,
        max_invalid_ratio_increase=0.0,
        max_unknown_ratio_increase=0.01,
    )
    assert len(regressions) == 1
    assert "unknown ratio regression" in regressions[0]
