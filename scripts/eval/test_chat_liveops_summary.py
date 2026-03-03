import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_liveops_summary.py"
    spec = importlib.util.spec_from_file_location("chat_liveops_summary", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_summary_counts_actions_and_pass_ratio(tmp_path: Path):
    module = _load_module()
    payloads = [
        {"generated_at": "a", "release_profile": {"release_signature": "s1"}, "release_train": {"decision": {"action": "promote"}}, "failures": []},
        {"generated_at": "b", "release_profile": {"release_signature": "s1"}, "release_train": {"decision": {"action": "hold"}}, "failures": ["x"]},
    ]
    for idx, payload in enumerate(payloads):
        path = tmp_path / f"chat_liveops_cycle_20260302_12000{idx}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
    rows = module.resolve_cycle_reports(tmp_path, prefix="chat_liveops_cycle", limit=10)
    summary = module.build_summary(rows)
    assert summary["window_size"] == 2
    assert summary["action_counts"]["promote"] == 1
    assert summary["action_counts"]["hold"] == 1
    assert summary["pass_ratio"] == 0.5


def test_evaluate_gate_detects_denied_action():
    module = _load_module()
    failures = module.evaluate_gate(
        {"window_size": 4, "pass_ratio": 1.0, "action_counts": {"rollback": 1}},
        min_window=3,
        min_pass_ratio=0.8,
        deny_actions={"rollback"},
    )
    assert len(failures) == 1
    assert "denied action observed: rollback" in failures[0]


def test_compare_with_baseline_detects_pass_ratio_and_rollback_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "pass_ratio": 1.0,
                "failure_total": 0,
                "action_counts": {"rollback": 0},
            }
        }
    }
    current = {
        "pass_ratio": 0.6,
        "failure_total": 2,
        "action_counts": {"rollback": 1},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_pass_ratio_drop=0.1,
        max_failure_total_increase=0,
        max_rollback_count_increase=0,
    )
    assert any("pass ratio regression" in item for item in failures)
    assert any("failure_total regression" in item for item in failures)
    assert any("rollback action regression" in item for item in failures)
