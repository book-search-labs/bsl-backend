import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_incident_feedback_binding.py"
    spec = importlib.util.spec_from_file_location("chat_incident_feedback_binding", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_classify_reason_code_maps_major_categories():
    module = _load_module()
    assert module.classify_reason_code("PROVIDER_TIMEOUT") == "LLM_TIMEOUT"
    assert module.classify_reason_code("TOOL_FAIL") == "TOOL_OUTAGE"
    assert module.classify_reason_code("insufficient_evidence") == "EVIDENCE_GAP"
    assert module.classify_reason_code("budget_gate_failed") == "COST_BURST"
    assert module.classify_reason_code("AUTHZ_DENY") == "AUTHZ_POLICY"


def test_build_binding_summary_combines_incident_and_triage():
    module = _load_module()
    summary = module.build_binding_summary(
        incident_reasons=["PROVIDER_TIMEOUT", "PROVIDER_TIMEOUT", "TOOL_FAIL"],
        triage_reasons=["TOOL_FAIL", "budget_gate_failed"],
    )
    assert summary["incident_reason_total"] == 3
    assert summary["triage_reason_total"] == 2
    assert summary["bound_category_total"] >= 2
    categories = {row["category"]: row for row in summary["categories"]}
    assert categories["LLM_TIMEOUT"]["incident"] == 2
    assert categories["TOOL_OUTAGE"]["total"] == 2


def test_build_recommendations_returns_non_empty():
    module = _load_module()
    summary = {
        "categories": [
            {"category": "LLM_TIMEOUT", "incident": 2, "triage": 1, "total": 3},
            {"category": "TOOL_OUTAGE", "incident": 1, "triage": 2, "total": 3},
        ]
    }
    recommendations = module.build_recommendations(summary, top_n=2)
    assert len(recommendations) == 2
    assert "LLM timeout" in recommendations[0] or "Tool outage" in recommendations[0]
