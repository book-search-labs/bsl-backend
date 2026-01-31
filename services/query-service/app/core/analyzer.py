from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.lid import detect_language
from app.core.normalize import normalize_query_details, tokenize

_HANGUL_SYLLABLE = re.compile(r"[가-힣]")
_HANGUL_JAMO = re.compile(r"[ㄱ-ㅎ]")
_LATIN = re.compile(r"[A-Za-z]")

_SERIES_KEYWORDS = ["시리즈", "세트", "전권", "완전판", "합본", "박스", "컬렉션"]


def analyze_query(raw: str, locale: str) -> dict[str, Any]:
    details = normalize_query_details(raw)
    nfkc = details["nfkc"]
    norm = details["norm"]
    nospace = norm.replace(" ", "")
    tokens = tokenize(norm)

    volume = _detect_volume(norm)
    isbn = _extract_isbn(nfkc)
    series_hint = _detect_series(norm)

    lang_info = detect_language(norm)
    lang = lang_info.get("detected") if isinstance(lang_info, dict) else "unknown"
    lang_conf = lang_info.get("confidence", 0.0) if isinstance(lang_info, dict) else 0.0

    is_mixed = _is_mixed(norm)
    is_chosung = _is_chosung(norm)
    is_isbn = isbn is not None

    mode = "normal"
    if is_isbn:
        mode = "isbn"
    elif is_chosung:
        mode = "chosung"
    elif is_mixed:
        mode = "mixed"

    canonical_key = _build_canonical_key(norm, mode, volume, isbn, series_hint, locale)
    confidence = _confidence_scores(mode, tokens, is_isbn)

    return {
        "raw": raw,
        "nfkc": nfkc,
        "norm": norm,
        "nospace": nospace,
        "tokens": tokens,
        "volume": volume,
        "isbn": isbn,
        "series": series_hint,
        "lang": lang or "unknown",
        "lang_confidence": lang_conf,
        "mode": mode,
        "is_mixed": is_mixed,
        "is_chosung": is_chosung,
        "is_isbn": is_isbn,
        "canonical_key": canonical_key,
        "confidence": confidence,
        "rules": details["rules"],
    }


def _detect_volume(norm: str) -> int | None:
    match = re.search(r"(\d+)권", norm)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_isbn(text: str) -> str | None:
    candidate = None
    for match in re.finditer(r"\b(?:isbn(?:-1[03])?:?\s*)?([0-9Xx\-\s]{10,17})\b", text, re.IGNORECASE):
        raw = match.group(1)
        digits = re.sub(r"[^0-9Xx]", "", raw)
        if len(digits) == 10 or len(digits) == 13:
            candidate = digits.upper()
            if _validate_isbn(candidate):
                return candidate
            if candidate:
                return candidate
    return candidate


def _validate_isbn(isbn: str) -> bool:
    if len(isbn) == 10:
        total = 0
        for idx, ch in enumerate(isbn):
            if ch == "X":
                value = 10
            elif ch.isdigit():
                value = int(ch)
            else:
                return False
            total += (idx + 1) * value
        return total % 11 == 0
    if len(isbn) == 13 and isbn.isdigit():
        total = 0
        for idx, ch in enumerate(isbn[:12]):
            factor = 1 if idx % 2 == 0 else 3
            total += int(ch) * factor
        check = (10 - (total % 10)) % 10
        return check == int(isbn[12])
    return False


def _detect_series(norm: str) -> str | None:
    for keyword in _SERIES_KEYWORDS:
        if keyword in norm:
            return keyword
    return None


def _is_mixed(text: str) -> bool:
    return bool(_HANGUL_SYLLABLE.search(text)) and bool(_LATIN.search(text))


def _is_chosung(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return False
    jamo_count = len(_HANGUL_JAMO.findall(stripped))
    syllable_count = len(_HANGUL_SYLLABLE.findall(stripped))
    latin_count = len(_LATIN.findall(stripped))
    if syllable_count > 0 or latin_count > 0:
        return False
    return jamo_count >= 2 and jamo_count / max(len(stripped), 1) >= 0.6


def _build_canonical_key(norm: str, mode: str, volume: int | None, isbn: str | None, series_hint: str | None, locale: str) -> str:
    parts = [norm, f"mode:{mode}", f"locale:{locale}"]
    if volume is not None:
        parts.append(f"vol:{volume}")
    if isbn:
        parts.append(f"isbn:{isbn}")
    if series_hint:
        parts.append(f"series:{series_hint}")
    base = "|".join(parts)
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"ck:{digest}"


def _confidence_scores(mode: str, tokens: list[str], is_isbn: bool) -> dict[str, float]:
    if is_isbn:
        return {"need_spell": 0.0, "need_rewrite": 0.0, "need_rerank": 0.2}
    base_spell = 0.2
    base_rewrite = 0.3
    base_rerank = 0.4
    if mode == "chosung":
        base_rewrite = 0.9
        base_spell = 0.4
    if len(tokens) <= 1:
        base_spell = max(base_spell, 0.4)
    if len(tokens) >= 4:
        base_rerank = max(base_rerank, 0.6)
    return {
        "need_spell": min(base_spell, 1.0),
        "need_rewrite": min(base_rewrite, 1.0),
        "need_rerank": min(base_rerank, 1.0),
    }
