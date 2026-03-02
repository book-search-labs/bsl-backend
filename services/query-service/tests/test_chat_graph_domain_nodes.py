from app.core.cache import CacheClient
from app.core.chat_graph import domain_nodes


def test_normalize_book_query_extracts_isbn_and_volume():
    parsed = domain_nodes.normalize_book_query("해리포터 시리즈 2권 ISBN 978-89-123-4567-8 추천")
    assert parsed["isbn"] == "9788912345678"
    assert parsed["volume"] == 2
    assert parsed["series_hint"] == "해리포터"


def test_resolve_selection_reference_by_ordinal():
    query, updated, unresolved = domain_nodes.resolve_selection_reference(
        "2번째 자세히 알려줘",
        {
            "last_candidates": [
                {"title": "A Book", "doc_id": "a1"},
                {"title": "B Book", "doc_id": "b1"},
            ],
            "selected_index": None,
            "selected_book": None,
        },
    )
    assert unresolved is False
    assert updated["selected_index"] == 1
    assert updated["selected_book"]["title"] == "B Book"
    assert query.startswith("B Book")


def test_resolve_selection_reference_requires_options_when_empty():
    query, _, unresolved = domain_nodes.resolve_selection_reference(
        "그거 환불 규정 알려줘",
        {"last_candidates": [], "selected_index": None, "selected_book": None},
    )
    assert unresolved is True
    assert query == "그거 환불 규정 알려줘"


def test_policy_topic_cache_save_and_load(monkeypatch):
    domain_nodes._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_POLICY_TOPIC_VERSION", "v2")
    response = {"status": "ok", "reason_code": "OK", "answer": {"role": "assistant", "content": "정책 안내"}}
    domain_nodes.save_policy_topic_cache("RefundPolicy", response, locale="ko-KR")

    loaded = domain_nodes.load_policy_topic_cache("RefundPolicy", locale="ko-KR")
    assert isinstance(loaded, dict)
    assert loaded["answer"]["content"] == "정책 안내"
