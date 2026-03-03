import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_graph_parity_eval.py"
    spec = importlib.util.spec_from_file_location("chat_graph_parity_eval", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_load_recent_run_rows(tmp_path: Path):
    module = _load_module()
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "run_1",
        "updated_at": 123,
        "checkpoints": [
            {"node": "load_state"},
            {"node": "policy_decide"},
            {"node": "execute"},
        ],
        "response": {"status": "ok", "reason_code": "OK"},
    }
    (runs_dir / "run_1.json").write_text(json.dumps(payload), encoding="utf-8")

    rows = module._load_recent_run_rows(tmp_path, limit=5)
    assert len(rows) == 1
    assert rows[0]["graph_run_id"] == "run_1"
    assert rows[0]["node_path"] == ["load_state", "policy_decide", "execute"]


def test_evaluate_gate_and_baseline():
    module = _load_module()
    derived = {
        "window_size": 100,
        "graph_run_count": 10,
        "mismatch_ratio": 0.08,
        "blocker_ratio": 0.01,
        "by_type": {"ACTION_DIFF": 5},
    }
    failures = module.evaluate_gate(
        derived,
        min_window=50,
        max_mismatch_ratio=0.1,
        max_blocker_ratio=0.02,
        min_graph_run_count=5,
    )
    assert failures == []

    baseline = {"derived": {"mismatch_ratio": 0.01, "blocker_ratio": 0.0}}
    regressions = module.compare_with_baseline(
        baseline,
        derived,
        max_mismatch_ratio_increase=0.02,
        max_blocker_ratio_increase=0.02,
        max_action_diff_ratio_increase=0.10,
        require_baseline_approval=False,
        max_baseline_age_days=0,
    )
    assert len(regressions) == 1
    assert "mismatch ratio regression" in regressions[0]


def test_compare_with_baseline_detects_action_diff_and_missing_approval():
    module = _load_module()
    baseline = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "baseline_meta": {},
        "derived": {
            "window_size": 100,
            "mismatch_ratio": 0.01,
            "blocker_ratio": 0.0,
            "by_type": {"ACTION_DIFF": 1},
        },
    }
    current = {
        "window_size": 100,
        "mismatch_ratio": 0.01,
        "blocker_ratio": 0.0,
        "by_type": {"ACTION_DIFF": 20},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_mismatch_ratio_increase=1.0,
        max_blocker_ratio_increase=1.0,
        max_action_diff_ratio_increase=0.05,
        require_baseline_approval=True,
        max_baseline_age_days=0,
    )
    assert any("action diff ratio regression" in item for item in failures)
    assert any("baseline metadata missing approved_by" in item for item in failures)
    assert any("baseline metadata missing approved_at" in item for item in failures)
    assert any("baseline metadata missing evidence" in item for item in failures)


def test_build_mismatch_samples_adds_primary_diff_type():
    module = _load_module()
    samples = [
        {"matched": True, "diff_types": []},
        {
            "matched": False,
            "ts": 1,
            "trace_id": "t1",
            "request_id": "r1",
            "intent": "BOOK_SEARCH",
            "topic": "RefundPolicy",
            "severity": "BLOCKER",
            "diff_types": ["CITATION_DIFF", "ACTION_DIFF"],
        },
    ]
    rows = module._build_mismatch_samples(samples, max_samples=5)
    assert len(rows) == 1
    assert rows[0]["primary_diff_type"] == "ACTION_DIFF"
    assert rows[0]["trace_id"] == "t1"
