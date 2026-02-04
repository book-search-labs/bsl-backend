from __future__ import annotations

import re
from typing import Any

_KEY_ALIASES = {
    "author": {"author", "저자"},
    "title": {"title", "제목"},
    "isbn": {"isbn"},
    "series": {"series", "시리즈"},
    "publisher": {"publisher", "출판사"},
}

_KEY_PATTERN = "|".join(sorted({alias for aliases in _KEY_ALIASES.values() for alias in aliases}, key=len, reverse=True))
_EXPLICIT_PATTERN = re.compile(rf"(?P<key>{_KEY_PATTERN})\s*:\s*(?P<value>\"[^\"]+\"|\S+)", re.IGNORECASE)


def parse_understanding(text: str) -> dict[str, Any]:
    if not text or not isinstance(text, str):
        return {
            "entities": _empty_entities(),
            "preferred_fields": [],
            "residual_text": "",
            "filters": [],
            "has_explicit": False,
        }

    matches = list(_EXPLICIT_PATTERN.finditer(text))
    if not matches:
        return {
            "entities": _empty_entities(),
            "preferred_fields": [],
            "residual_text": text.strip(),
            "filters": [],
            "has_explicit": False,
        }

    entities = _empty_entities()
    preferred_fields: list[str] = []
    isbn_values: list[str] = []

    for match in matches:
        raw_key = match.group("key").lower()
        value = match.group("value").strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].strip()
        canonical_key = _canonical_key(raw_key)
        if not canonical_key or not value:
            continue
        if canonical_key == "isbn":
            normalized = _normalize_isbn(value)
            if normalized:
                isbn_values.append(normalized)
                entities[canonical_key].append(normalized)
            continue
        entities[canonical_key].append(value)
        logical_field = _logical_field_for(canonical_key)
        if logical_field and logical_field not in preferred_fields:
            preferred_fields.append(logical_field)

    residual = _EXPLICIT_PATTERN.sub(" ", text)
    residual = re.sub(r"\s+", " ", residual).strip()

    filters: list[dict[str, Any]] = []
    if isbn_values:
        filters.append(
            {
                "and": [
                    {
                        "scope": "CATALOG",
                        "logicalField": "isbn13",
                        "op": "eq",
                        "value": isbn_values if len(isbn_values) > 1 else isbn_values[0],
                    }
                ]
            }
        )

    return {
        "entities": entities,
        "preferred_fields": preferred_fields,
        "residual_text": residual,
        "filters": filters,
        "has_explicit": True,
    }


def _empty_entities() -> dict[str, list[str]]:
    return {"title": [], "author": [], "publisher": [], "series": [], "isbn": []}


def _canonical_key(raw_key: str) -> str | None:
    for canonical, aliases in _KEY_ALIASES.items():
        if raw_key in aliases:
            return canonical
    return None


def _logical_field_for(key: str) -> str | None:
    if key == "author":
        return "author_ko"
    if key == "title":
        return "title_ko"
    if key == "series":
        return "series_ko"
    if key == "publisher":
        return "publisher"
    return None


def _normalize_isbn(value: str) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", value)
    if len(cleaned) == 13 and cleaned.isdigit():
        return cleaned
    if len(cleaned) == 10:
        normalized = _isbn10_to_13(cleaned.upper())
        return normalized
    return None


def _isbn10_to_13(isbn10: str) -> str | None:
    if len(isbn10) != 10:
        return None
    core = "978" + isbn10[:-1]
    if not core.isdigit():
        return None
    total = 0
    for idx, ch in enumerate(core):
        factor = 1 if idx % 2 == 0 else 3
        total += int(ch) * factor
    check = (10 - (total % 10)) % 10
    return f"{core}{check}"
