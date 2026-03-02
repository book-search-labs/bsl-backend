import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_capacity_cost_guard.py"
    spec = importlib.util.spec_from_file_location("chat_capacity_cost_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_audit_counts_and_rates():
    module = _load_module()
    rows = [
        {"status": "ok", "tokens": 100, "cost_usd": 0.01, "reason_code": "NONE"},
        {"status": "error", "tokens": 80, "cost_usd": 0.03, "reason_code": "PROVIDER_TIMEOUT"},
        {"status": "ok", "tokens": 40, "cost_usd": 0.01, "reason_code": "NONE"},
    ]
    summary = module.summarize_audit(rows, window_minutes=60)
    assert summary["window_size"] == 3
    assert summary["error_total"] == 1
    assert abs(summary["error_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["total_tokens"] == 220
    assert abs(summary["cost_usd_per_hour"] - 0.05) < 1e-9


def test_decide_guard_mode_escalates_to_fail_closed():
    module = _load_module()
    decision = module.decide_guard_mode(
        audit_summary={
            "error_ratio": 0.30,
            "cost_usd_per_hour": 30.0,
            "tokens_per_hour": 100000.0,
        },
        perf_summary={"llm_count": 10, "llm_p95_ms": 8000.0, "fallback_ratio": 0.40},
        completion_summary={"insufficient_evidence_ratio": 0.55},
        max_audit_error_ratio=0.08,
        max_cost_usd_per_hour=5.0,
        max_tokens_per_hour=300000.0,
        max_llm_p95_ms=4000.0,
        max_fallback_ratio=0.15,
        max_insufficient_evidence_ratio=0.30,
    )
    assert decision["mode"] == "FAIL_CLOSED"
    assert len(decision["severe_breaches"]) >= 2


def test_read_audit_rows_applies_window_filter(tmp_path: Path):
    module = _load_module()
    path = tmp_path / "audit.log"
    path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-03-02T00:00:00+00:00","status":"ok","tokens":10,"cost_usd":0.01}',
                '{"timestamp":"2026-03-02T11:55:00+00:00","status":"ok","tokens":20,"cost_usd":0.02}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = module.read_audit_rows(
        path,
        window_minutes=10,
        limit=100,
        now=datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert int(rows[0]["tokens"]) == 20


def test_evaluate_gate_respects_max_mode():
    module = _load_module()
    failures = module.evaluate_gate({"mode": "DEGRADE_LEVEL_2"}, max_mode="DEGRADE_LEVEL_1")
    assert len(failures) == 1
    assert "capacity guard mode exceeded" in failures[0]
