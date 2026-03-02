import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_production_launch_gate.py"
    spec = importlib.util.spec_from_file_location("chat_production_launch_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_completion_summary_counts_commerce_completion():
    module = _load_module()
    rows = [
        {"intent": "ORDER_STATUS", "status": "ok", "next_action": "NONE"},
        {"intent": "REFUND_REQUEST", "status": "insufficient_evidence", "next_action": "PROVIDE_REQUIRED_INFO"},
        {"intent": "BOOK_SEARCH", "status": "ok", "next_action": "NONE"},
    ]
    summary = module.build_completion_summary(rows)
    assert summary["run_total"] == 3
    assert summary["commerce_total"] == 2
    assert summary["commerce_completed_total"] == 1
    assert summary["commerce_completion_rate"] == 0.5
    assert summary["insufficient_evidence_ratio"] > 0.0


def test_completion_summary_from_launch_metrics_payload():
    module = _load_module()
    summary = module.completion_summary_from_launch_metrics(
        {
            "total": 10,
            "insufficient_total": 2,
            "insufficient_ratio": 0.2,
            "by_intent": {"ORDER_STATUS": {"total": 6, "completed_total": 5}},
            "by_domain": {"commerce": {"total": 6, "completed_total": 5, "completion_rate": 0.8333}},
        }
    )
    assert summary["run_total"] == 10
    assert summary["insufficient_evidence_total"] == 2
    assert summary["commerce_total"] == 6
    assert summary["commerce_completed_total"] == 5
    assert summary["commerce_unresolved_total"] == 1
    assert summary["commerce_completion_rate"] > 0.8


def test_load_recent_runs_reads_intent_from_checkpoint(tmp_path: Path):
    module = _load_module()
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "run_a",
        "updated_at": 200,
        "checkpoints": [{"state": {"intent": "ORDER_STATUS"}}],
        "response": {"status": "ok", "reason_code": "OK", "next_action": "NONE"},
    }
    (runs_dir / "run_a.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = module.load_recent_runs(tmp_path, limit=10)
    assert len(rows) == 1
    assert rows[0]["intent"] == "ORDER_STATUS"
    assert rows[0]["status"] == "ok"


def test_evaluate_gate_reports_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        parity_payload={"mismatch_ratio": 0.2, "blocker_ratio": 0.03},
        canary_decision={"passed": False, "reason": "blocker_ratio_exceeded"},
        budget_decision={"passed": False, "failures": ["llm p95 exceeded"]},
        reason_summary={"window_size": 5, "invalid_ratio": 0.1, "unknown_ratio": 0.2},
        legacy_summary={"window_size": 4, "legacy_count": 2, "legacy_ratio": 0.5},
        completion_summary={
            "run_total": 4,
            "commerce_total": 2,
            "commerce_completion_rate": 0.5,
            "insufficient_evidence_ratio": 0.5,
        },
        min_reason_window=20,
        min_legacy_window=20,
        min_run_window=20,
        min_commerce_samples=10,
        max_mismatch_ratio=0.1,
        max_blocker_ratio=0.02,
        max_reason_invalid_ratio=0.0,
        max_reason_unknown_ratio=0.05,
        max_legacy_ratio=0.0,
        max_legacy_count=0,
        min_commerce_completion_rate=0.9,
        max_insufficient_evidence_ratio=0.3,
    )
    assert len(failures) >= 8
    assert any("canary gate failed" in item for item in failures)
    assert any("budget gate failed" in item for item in failures)
    assert any("commerce completion rate below threshold" in item for item in failures)


def test_evaluate_gate_passes_with_healthy_inputs():
    module = _load_module()
    failures = module.evaluate_gate(
        parity_payload={"mismatch_ratio": 0.01, "blocker_ratio": 0.0},
        canary_decision={"passed": True, "reason": "within_threshold"},
        budget_decision={"passed": True, "failures": []},
        reason_summary={"window_size": 100, "invalid_ratio": 0.0, "unknown_ratio": 0.01},
        legacy_summary={"window_size": 100, "legacy_count": 0, "legacy_ratio": 0.0},
        completion_summary={
            "run_total": 120,
            "commerce_total": 30,
            "commerce_completion_rate": 0.95,
            "insufficient_evidence_ratio": 0.1,
        },
        min_reason_window=20,
        min_legacy_window=20,
        min_run_window=20,
        min_commerce_samples=10,
        max_mismatch_ratio=0.1,
        max_blocker_ratio=0.02,
        max_reason_invalid_ratio=0.0,
        max_reason_unknown_ratio=0.05,
        max_legacy_ratio=0.0,
        max_legacy_count=0,
        min_commerce_completion_rate=0.9,
        max_insufficient_evidence_ratio=0.3,
    )
    assert failures == []
