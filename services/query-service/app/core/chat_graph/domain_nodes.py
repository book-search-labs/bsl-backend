from __future__ import annotations

import os
import re
from typing import Any, Mapping

from app.core.cache import get_cache

_CACHE = get_cache()

_ORDINAL_RE = re.compile(r"(?:(\d{1,2})\s*(?:번째|번)|(?:제\s*(\d{1,2})\s*권))")
_ISBN_RE = re.compile(r"\b(?:97[89][-\s]?)?\d{9}[\dXx]\b")


def _selection_cache_key(session_id: str) -> str:
    return f"chat:graph:selection:{session_id}"


def _selection_ttl_sec() -> int:
    return max(600, int(os.getenv("QS_CHAT_SELECTION_TTL_SEC", "86400")))


def _policy_cache_key(topic: str, *, locale: str, policy_version: str) -> str:
    return f"chat:graph:policy-cache:{locale}:{policy_version}:{topic}"


def _policy_cache_ttl_sec() -> int:
    return max(30, int(os.getenv("QS_CHAT_POLICY_CACHE_TTL_SEC", "300")))


def _policy_version() -> str:
    return str(os.getenv("QS_CHAT_POLICY_TOPIC_VERSION", "v1")).strip() or "v1"


def normalize_book_query(query: str) -> dict[str, Any]:
    raw = str(query or "").strip()
    lower = raw.lower()
    isbn_match = _ISBN_RE.search(raw.replace(" ", ""))
    isbn = isbn_match.group(0).replace("-", "").replace(" ", "") if isbn_match else None

    volume = None
    volume_match = re.search(r"(?:제\s*)?(\d{1,2})\s*(?:권|편|volume|vol\.?)", lower)
    if volume_match:
        try:
            volume = int(volume_match.group(1))
        except Exception:
            volume = None

    series_hint = None
    series_match = re.search(r"([0-9a-zA-Z가-힣\s]+)\s*(?:시리즈|series)", raw)
    if series_match:
        series_hint = " ".join(series_match.group(1).split())

    title_hint = raw
    for token in ["추천", "비슷한", "그거", "그 책", "아까 추천한", "policy", "정책"]:
        title_hint = title_hint.replace(token, " ")
    title_hint = " ".join(title_hint.split())
    if len(title_hint) < 2:
        title_hint = ""

    return {
        "query": raw,
        "isbn": isbn,
        "volume": volume,
        "series_hint": series_hint or "",
        "title_hint": title_hint,
    }


def classify_policy_topic(query: str) -> str | None:
    q = str(query or "").strip().lower()
    if not q:
        return None
    policy_words = ("정책", "규정", "기준", "수수료", "안내", "절차", "policy", "guide")
    if not any(word in q for word in policy_words):
        return None
    if any(word in q for word in ("ebook", "전자책")) and any(word in q for word in ("refund", "환불")):
        return "EbookRefundPolicy"
    if any(word in q for word in ("refund", "환불", "반품")):
        return "RefundPolicy"
    if any(word in q for word in ("shipping", "배송", "택배")):
        return "ShippingPolicy"
    if any(word in q for word in ("cancel", "취소")):
        return "OrderCancelPolicy"
    return "OrderPolicy"


def is_policy_read_lane(query: str, intent: str | None) -> bool:
    topic = classify_policy_topic(query)
    if not topic:
        return False
    q = str(query or "").lower()
    if any(word in q for word in ("취소해", "환불해", "진행", "처리", "실행", "confirm", "확인")):
        return False
    if str(intent or "").upper() in {"REFUND", "ORDER"} and any(word in q for word in ("요청", "request")):
        return False
    return True


def load_policy_topic_cache(topic: str, *, locale: str) -> dict[str, Any] | None:
    cached = _CACHE.get_json(_policy_cache_key(topic, locale=locale, policy_version=_policy_version()))
    if isinstance(cached, Mapping):
        payload = cached.get("response")
        if isinstance(payload, Mapping):
            return dict(payload)
    return None


def save_policy_topic_cache(topic: str, response: Mapping[str, Any], *, locale: str) -> None:
    if not topic:
        return
    payload = {
        "topic": topic,
        "policy_version": _policy_version(),
        "response": dict(response),
    }
    _CACHE.set_json(
        _policy_cache_key(topic, locale=locale, policy_version=_policy_version()),
        payload,
        ttl=_policy_cache_ttl_sec(),
    )


def load_selection_memory(session_id: str) -> dict[str, Any]:
    cached = _CACHE.get_json(_selection_cache_key(session_id))
    if isinstance(cached, Mapping):
        raw_candidates = cached.get("last_candidates")
        candidates = [dict(item) for item in raw_candidates if isinstance(item, Mapping)] if isinstance(raw_candidates, list) else []
        selected_index = cached.get("selected_index")
        selected_book = cached.get("selected_book")
        return {
            "last_candidates": candidates,
            "selected_index": int(selected_index) if isinstance(selected_index, int) and selected_index >= 0 else None,
            "selected_book": dict(selected_book) if isinstance(selected_book, Mapping) else None,
        }
    return {"last_candidates": [], "selected_index": None, "selected_book": None}


def save_selection_memory(session_id: str, selection: Mapping[str, Any]) -> None:
    payload = {
        "last_candidates": [dict(item) for item in selection.get("last_candidates", []) if isinstance(item, Mapping)],
        "selected_index": selection.get("selected_index"),
        "selected_book": dict(selection.get("selected_book")) if isinstance(selection.get("selected_book"), Mapping) else None,
    }
    _CACHE.set_json(_selection_cache_key(session_id), payload, ttl=_selection_ttl_sec())


def resolve_selection_reference(
    query: str,
    selection: Mapping[str, Any],
) -> tuple[str, dict[str, Any], bool]:
    raw_query = str(query or "").strip()
    updated = {
        "last_candidates": [dict(item) for item in selection.get("last_candidates", []) if isinstance(item, Mapping)],
        "selected_index": selection.get("selected_index") if isinstance(selection.get("selected_index"), int) else None,
        "selected_book": dict(selection.get("selected_book")) if isinstance(selection.get("selected_book"), Mapping) else None,
    }
    if not raw_query:
        return raw_query, updated, False

    lowered = raw_query.lower()
    ordinal = _extract_ordinal(raw_query)
    if ordinal is not None:
        idx = ordinal - 1
        candidates = updated.get("last_candidates") or []
        if isinstance(candidates, list) and 0 <= idx < len(candidates):
            selected = dict(candidates[idx])
            updated["selected_index"] = idx
            updated["selected_book"] = selected
            title = str(selected.get("title") or selected.get("doc_id") or "").strip()
            if title:
                return f"{title} {raw_query}".strip(), updated, False
        return raw_query, updated, True

    pronoun_ref = any(token in lowered for token in ("그거", "그 책", "그 도서", "아까 추천"))
    if pronoun_ref:
        selected = updated.get("selected_book")
        if isinstance(selected, Mapping):
            title = str(selected.get("title") or selected.get("doc_id") or "").strip()
            if title:
                return f"{title} {raw_query}".strip(), updated, False
        candidates = updated.get("last_candidates")
        if isinstance(candidates, list) and candidates:
            first = dict(candidates[0])
            updated["selected_index"] = 0
            updated["selected_book"] = first
            title = str(first.get("title") or first.get("doc_id") or "").strip()
            if title:
                return f"{title} {raw_query}".strip(), updated, False
        return raw_query, updated, True

    return raw_query, updated, False


def derive_candidates_from_response(response: Mapping[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    sources = response.get("sources")
    if not isinstance(sources, list):
        return []

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        title = str(source.get("title") or "").strip()
        doc_id = str(source.get("doc_id") or source.get("chunk_id") or "").strip()
        key = (title or doc_id).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "title": title,
                "doc_id": doc_id,
                "isbn": str(source.get("isbn") or "").strip(),
                "author": str(source.get("author") or "").strip(),
            }
        )
        if len(candidates) >= max(1, int(limit)):
            break
    return candidates


def _extract_ordinal(query: str) -> int | None:
    match = _ORDINAL_RE.search(str(query or ""))
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    if not raw:
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    if value <= 0:
        return None
    return value
