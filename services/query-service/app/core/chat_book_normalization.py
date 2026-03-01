from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BookQuerySlots:
    isbn: str | None
    title: str | None
    series: str | None
    volume: int | None
    format: str | None


_QUOTED_TITLE_PATTERNS = [
    r"[\"'“”‘’「」『』《》〈〉]\s*([^\"'“”‘’「」『』《》〈〉]{2,120})\s*[\"'“”‘’「」『』《》〈〉]",
]
_ISBN_CANDIDATE_RE = re.compile(r"(?<![0-9Xx])(?:97[89][0-9\-\s]{10,17}[0-9]|[0-9][0-9\-\s]{8,14}[0-9Xx])(?![0-9Xx])")
_VOLUME_RE = re.compile(
    (
        r"(?:vol(?:ume)?\.?\s*([ivxlcdm]{1,8}|\d{1,3})"
        r"|제\s*([ivxlcdm]{1,8}|\d{1,3})\s*(?:권|편|부)"
        r"|([ivxlcdm]{1,8}|\d{1,3})\s*(?:권|편|부|vol(?:ume)?\.?))"
    ),
    flags=re.IGNORECASE,
)
_SERIES_RE = re.compile(r"(?:series|시리즈)\s*[:：]?\s*([^\s,]{1,80})", flags=re.IGNORECASE)
_EDITION_TOKEN_RE = re.compile(
    (
        r"(?:\b\d{1,2}(?:st|nd|rd|th)\s+edition\b"
        r"|\brevised\s+edition\b"
        r"|\bupdated\s+edition\b"
        r"|\banniversary\s+edition\b"
        r"|개정판|개정증보판|증보판|개정)"
    ),
    flags=re.IGNORECASE,
)


def _normalize_space(text: str) -> str:
    return " ".join((text or "").strip().split())


def _isbn_checksum10(code: str) -> bool:
    if len(code) != 10:
        return False
    total = 0
    for idx, token in enumerate(code):
        if idx == 9 and token.upper() == "X":
            value = 10
        elif token.isdigit():
            value = int(token)
        else:
            return False
        total += (10 - idx) * value
    return total % 11 == 0


def _isbn_checksum13(code: str) -> bool:
    if len(code) != 13 or not code.isdigit():
        return False
    total = 0
    for idx, token in enumerate(code):
        value = int(token)
        total += value if idx % 2 == 0 else value * 3
    return total % 10 == 0


def _isbn10_to13(code10: str) -> str:
    body = f"978{code10[:9]}"
    total = 0
    for idx, token in enumerate(body):
        digit = int(token)
        total += digit if idx % 2 == 0 else digit * 3
    check_digit = (10 - (total % 10)) % 10
    return f"{body}{check_digit}"


def normalize_isbn(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"[\-\s]", "", value).upper()
    if len(compact) == 10 and _isbn_checksum10(compact):
        return _isbn10_to13(compact)
    if len(compact) == 13 and _isbn_checksum13(compact):
        return compact
    return None


def extract_isbn(query: str) -> str | None:
    if not query:
        return None
    for candidate in _ISBN_CANDIDATE_RE.findall(query):
        normalized = normalize_isbn(candidate)
        if normalized:
            return normalized
    return None


def extract_title(query: str) -> str | None:
    raw = str(query or "").strip()
    if not raw:
        return None
    for pattern in _QUOTED_TITLE_PATTERNS:
        matched = re.search(pattern, raw)
        if not matched:
            continue
        title = _normalize_space(str(matched.group(1) or ""))
        if len(title) >= 2:
            return title
    return None


def extract_series(query: str) -> str | None:
    matched = _SERIES_RE.search(str(query or ""))
    if not matched:
        return None
    series = _normalize_space(str(matched.group(1) or ""))
    if len(series) < 1:
        return None
    return series[:80]


def extract_volume(query: str) -> int | None:
    matched = _VOLUME_RE.search(str(query or ""))
    if not matched:
        return None
    try:
        token = next((group for group in matched.groups() if isinstance(group, str) and group.strip()), "")
        if token.isdigit():
            parsed = int(token)
        else:
            parsed = _parse_roman_number(token)
    except Exception:
        return None
    if parsed <= 0:
        return None
    return parsed


def extract_book_format(query: str) -> str | None:
    normalized = str(query or "").lower()
    if any(token in normalized for token in ["ebook", "e-book", "전자책"]):
        return "ebook"
    if any(token in normalized for token in ["종이책", "paperback", "hardcover", "양장", "무선"]):
        return "print"
    return None


def _parse_roman_number(token: str) -> int:
    roman = str(token or "").strip().upper()
    if not roman:
        raise ValueError("empty roman token")
    mapping = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(roman):
        value = mapping.get(ch)
        if value is None:
            raise ValueError("invalid roman token")
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    if total <= 0:
        raise ValueError("invalid roman value")
    return total


def _canonicalize_title(value: str) -> str:
    normalized = _normalize_space(value)
    if not normalized:
        return normalized
    cleaned = _EDITION_TOKEN_RE.sub(" ", normalized)
    cleaned = _normalize_space(cleaned.strip(" -_/()[]"))
    return cleaned or normalized


def extract_book_query_slots(query: str) -> BookQuerySlots:
    return BookQuerySlots(
        isbn=extract_isbn(query),
        title=_canonicalize_title(str(extract_title(query) or "")) or None,
        series=extract_series(query),
        volume=extract_volume(query),
        format=extract_book_format(query),
    )


def canonical_book_query(slots: BookQuerySlots, fallback_query: str) -> str:
    if isinstance(slots.isbn, str) and slots.isbn:
        return slots.isbn
    if isinstance(slots.title, str) and slots.title:
        return _canonicalize_title(slots.title)
    fallback = _canonicalize_title(_normalize_space(fallback_query))
    if not fallback:
        return ""
    return fallback


def slots_to_dict(slots: BookQuerySlots) -> dict[str, Any]:
    return {
        "isbn": slots.isbn,
        "title": slots.title,
        "series": slots.series,
        "volume": slots.volume,
        "format": slots.format,
    }
