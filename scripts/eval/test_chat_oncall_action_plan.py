import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_oncall_action_plan.py"
    spec = importlib.util.spec_from_file_location("chat_oncall_action_plan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_plan_ranks_top_reasons():
    module = _load_module()
    rows = [
        {"source": "gate_failure", "reason_code": "LAUNCH_GATE_FAILURE", "severity": "BLOCKER"},
        {"source": "completion", "reason_code": "PROVIDER_TIMEOUT", "severity": "WARN"},
        {"source": "completion", "reason_code": "PROVIDER_TIMEOUT", "severity": "WARN"},
    ]
    plan = module.build_plan(rows, top_n=2)
    assert plan["case_total"] == 3
    assert plan["top_reasons"][0]["reason_code"] == "PROVIDER_TIMEOUT"
    assert plan["reason_counts"]["PROVIDER_TIMEOUT"] == 2
    assert len(plan["actions"]) >= 1


def test_read_jsonl_parses_rows(tmp_path: Path):
    module = _load_module()
    path = tmp_path / "triage.jsonl"
    path.write_text('{"reason_code":"A"}\n{"reason_code":"B"}\n', encoding="utf-8")
    rows = module.read_jsonl(path)
    assert len(rows) == 2


def test_compare_with_baseline_detects_case_blocker_unknown_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "case_total": 1,
                "severity_counts": {"BLOCKER": 0},
                "reason_counts": {"unknown": 0},
            }
        }
    }
    current = {
        "case_total": 5,
        "severity_counts": {"BLOCKER": 2},
        "reason_counts": {"unknown": 3},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_case_total_increase=1,
        max_blocker_increase=0,
        max_unknown_reason_increase=0,
    )
    assert any("case_total regression" in item for item in failures)
    assert any("blocker_count regression" in item for item in failures)
    assert any("unknown_reason regression" in item for item in failures)
