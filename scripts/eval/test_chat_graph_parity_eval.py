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
    )
    assert len(regressions) == 1
    assert "mismatch ratio regression" in regressions[0]
