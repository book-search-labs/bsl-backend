from app.core.cache import CacheClient
from app.core.chat_graph import launch_metrics
from app.core.metrics import metrics


def test_record_launch_metrics_updates_intent_and_domain_summary():
    launch_metrics._CACHE = CacheClient(None)

    launch_metrics.record_launch_metrics(
        intent="ORDER_STATUS",
        status="ok",
        next_action="NONE",
        reason_code="OK",
    )
    launch_metrics.record_launch_metrics(
        intent="ORDER_STATUS",
        status="insufficient_evidence",
        next_action="RETRY",
        reason_code="RAG_NO_CHUNKS",
    )

    summary = launch_metrics.load_launch_metrics_summary()
    assert summary["total"] == 2
    assert summary["completed_total"] == 1
    assert summary["insufficient_total"] == 1

    by_intent = summary["by_intent"]["ORDER_STATUS"]
    assert by_intent["total"] == 2
    assert by_intent["completed_total"] == 1
    assert by_intent["insufficient_total"] == 1
    assert by_intent["completion_rate"] == 0.5
    assert by_intent["insufficient_ratio"] == 0.5

    by_domain = summary["by_domain"]["commerce"]
    assert by_domain["total"] == 2
    assert by_domain["insufficient_total"] == 1
    assert by_domain["insufficient_ratio"] == 0.5

    snapshot = metrics.snapshot()
    assert any(key.startswith("chat_completion_rate{intent=ORDER_STATUS}") for key in snapshot.keys())
    assert any(key.startswith("chat_insufficient_evidence_rate{domain=commerce}") for key in snapshot.keys())
