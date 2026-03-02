from app.core.cache import CacheClient
from app.core.chat_graph import perf_budget


def test_append_perf_sample_and_build_summary():
    perf_budget._CACHE = CacheClient(None)
    for idx in range(10):
        perf_budget.append_perf_sample(
            trace_id=f"t{idx}",
            request_id=f"r{idx}",
            session_id="u:perf:default",
            engine_mode="agent",
            route="ANSWER",
            status="ok",
            runtime_ms=100 + idx * 10,
            llm_path=(idx % 2 == 0),
            tool_calls=1,
        )

    summary = perf_budget.build_perf_summary(limit=20)
    assert summary["window_size"] == 10
    assert summary["llm_count"] == 5
    assert summary["non_llm_count"] == 5
    assert summary["avg_tool_calls"] == 1.0


def test_evaluate_budget_gate_failure(monkeypatch):
    monkeypatch.setenv("QS_CHAT_BUDGET_MIN_WINDOW", "1")
    monkeypatch.setenv("QS_CHAT_BUDGET_MAX_FALLBACK_RATIO", "0.05")
    summary = {
        "window_size": 10,
        "non_llm_count": 10,
        "llm_count": 0,
        "non_llm_p95_ms": 100.0,
        "llm_p95_ms": 0.0,
        "avg_tool_calls": 1.0,
        "fallback_ratio": 0.20,
    }
    decision = perf_budget.evaluate_budget_gate(summary)
    assert decision.passed is False
    assert any("fallback ratio exceeded" in item for item in decision.failures)


def test_evaluate_cutover_decision_promote_and_hold(monkeypatch):
    monkeypatch.setenv("QS_CHAT_BUDGET_MIN_WINDOW", "1")
    monkeypatch.setenv("QS_CHAT_CUTOVER_MIN_DWELL_MIN", "30")
    summary = {
        "window_size": 20,
        "non_llm_count": 20,
        "llm_count": 0,
        "non_llm_p95_ms": 100.0,
        "llm_p95_ms": 0.0,
        "avg_tool_calls": 1.0,
        "fallback_ratio": 0.0,
    }
    hold = perf_budget.evaluate_cutover_decision(summary, current_stage=10, dwell_minutes=10)
    assert hold.action == "hold"
    promote = perf_budget.evaluate_cutover_decision(summary, current_stage=10, dwell_minutes=35)
    assert promote.action == "promote"
    assert promote.next_stage == 25
