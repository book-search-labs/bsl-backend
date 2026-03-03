import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_cost_optimizer_policy.py"
    spec = importlib.util.spec_from_file_location("chat_cost_optimizer_policy", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_cost_events_tracks_resolution_and_cost():
    module = _load_module()
    rows = [
        {
            "intent": "book_recommend",
            "risk_level": "low",
            "resolved": True,
            "session_cost_usd": 1.0,
            "tool_calls": 1,
            "rewrite_steps": 1,
            "route_profile": "HEAVY",
        },
        {
            "intent": "refund_request",
            "risk_level": "high",
            "resolved": False,
            "session_cost_usd": 2.0,
            "tool_calls": 2,
            "rewrite_steps": 2,
            "route_profile": "TRUSTED",
        },
    ]
    summary = module.summarize_cost_events(rows)
    assert summary["window_size"] == 2
    assert summary["resolved_total"] == 1
    assert summary["resolution_rate"] == 0.5
    assert abs(summary["cost_per_resolved_session"] - 1.0) < 1e-9
    assert summary["heavy_route_ratio"] == 1.0


def test_decide_optimizer_policy_soft_clamp_preserves_high_risk():
    module = _load_module()
    summary = {
        "window_size": 2,
        "intents": [
            {
                "intent": "BOOK_RECOMMEND",
                "risk_level": "LOW",
                "resolved_total": 10,
                "resolution_rate": 0.9,
                "cost_per_resolved_session": 4.0,
            },
            {
                "intent": "REFUND_REQUEST",
                "risk_level": "HIGH",
                "resolved_total": 3,
                "resolution_rate": 0.95,
                "cost_per_resolved_session": 3.0,
            },
        ],
    }
    decision = module.decide_optimizer_policy(
        summary,
        budget_utilization=0.8,
        soft_budget_utilization=0.75,
        hard_budget_utilization=0.9,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.5,
        high_risk_intents={"REFUND_REQUEST"},
    )
    by_intent = {row["intent"]: row for row in decision["intent_policies"]}
    assert decision["mode"] == "SOFT_CLAMP"
    assert by_intent["BOOK_RECOMMEND"]["route_policy"] == "LIGHT"
    assert by_intent["REFUND_REQUEST"]["route_policy"] == "TRUSTED"


def test_evaluate_gate_blocks_high_risk_light_route():
    module = _load_module()
    failures = module.evaluate_gate(
        {"window_size": 10},
        {
            "mode": "SOFT_CLAMP",
            "budget_utilization": 0.8,
            "intent_policies": [
                {"intent": "REFUND_REQUEST", "risk_level": "HIGH", "route_policy": "LIGHT", "resolution_rate": 0.9}
            ],
        },
        min_window=1,
        min_resolution_rate=0.8,
        soft_budget_utilization=0.75,
        hard_budget_utilization=0.9,
        require_clamp=True,
    )
    assert len(failures) == 1
    assert "high-risk intent downgraded" in failures[0]


def test_evaluate_gate_passes_empty_window_when_min_window_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {"window_size": 0},
        {"mode": "NORMAL", "budget_utilization": 0.0, "intent_policies": []},
        min_window=0,
        min_resolution_rate=0.8,
        soft_budget_utilization=0.75,
        hard_budget_utilization=0.9,
        require_clamp=False,
    )
    assert failures == []


def test_compare_with_baseline_detects_cost_and_high_risk_light_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "resolution_rate": 0.90,
                "cost_per_resolved_session": 1.20,
                "heavy_route_ratio": 0.40,
                "avg_rewrite_steps": 1.0,
            }
        },
        "decision": {
            "intent_policies": [
                {"intent": "REFUND_REQUEST", "risk_level": "HIGH", "route_policy": "TRUSTED"},
            ]
        },
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "resolution_rate": 0.80,
            "cost_per_resolved_session": 1.90,
            "heavy_route_ratio": 0.60,
            "avg_rewrite_steps": 1.8,
        },
        {
            "intent_policies": [
                {"intent": "REFUND_REQUEST", "risk_level": "HIGH", "route_policy": "LIGHT"},
            ]
        },
        max_resolution_rate_drop=0.05,
        max_cost_per_resolved_session_increase=0.50,
        max_heavy_route_ratio_increase=0.10,
        max_avg_rewrite_steps_increase=0.50,
        max_high_risk_light_increase=0,
    )
    assert len(failures) == 5
