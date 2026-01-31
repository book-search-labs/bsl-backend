import json
import os
import re
import unicodedata

CONTROL_WHITESPACE = {"\t", "\n", "\r", "\v", "\f"}
_RULES_LOADED = False
_REPLACEMENTS: list[tuple[object, str, bool]] = []

try:  # optional ICU normalization
    from icu import Normalizer2  # type: ignore

    _ICU_NFKC = Normalizer2.getNFKCInstance()
except Exception:  # pragma: no cover - optional dependency
    _ICU_NFKC = None

_PUNCTUATION_TO_SPACE = re.compile(r"[·•∙・ㆍ:_\\-–—−/|,;]+")


def normalize_query(raw: str) -> str:
    details = normalize_query_details(raw)
    return details["norm"]


def normalize_query_details(raw: str) -> dict:
    if raw is None:
        raise ValueError("missing_raw")
    rules = []
    nfkc = _nfkc(raw)
    if nfkc != raw:
        rules.append("nfkc")
    cleaned = _strip_control_chars(nfkc)
    if cleaned != nfkc:
        rules.append("strip_control")
    cleaned = cleaned.strip()
    rules.append("trim")
    cleaned = cleaned.casefold()
    rules.append("casefold")
    before = cleaned
    cleaned = _normalize_punctuation(cleaned)
    if cleaned != before:
        rules.append("normalize_punct")
    before = cleaned
    cleaned = _normalize_volume_tokens(cleaned)
    if cleaned != before:
        rules.append("normalize_volume")
    cleaned = re.sub(r"\s+", " ", cleaned)
    rules.append("collapse_whitespace")
    before = cleaned
    cleaned = _apply_replacements(cleaned)
    if cleaned != before:
        rules.append("replace_rules")
    if cleaned == "":
        raise ValueError("empty_query")
    return {"nfkc": nfkc, "norm": cleaned, "rules": rules}


def tokenize(normalized: str) -> list[str]:
    return [token for token in normalized.split(" ") if token]


def _strip_control_chars(value: str) -> str:
    cleaned = []
    for ch in value:
        code = ord(ch)
        if code < 32 or code == 127:
            if ch in CONTROL_WHITESPACE:
                cleaned.append(" ")
            continue
        cleaned.append(ch)
    return "".join(cleaned)


def _nfkc(value: str) -> str:
    if _ICU_NFKC is not None:
        try:
            return _ICU_NFKC.normalize(value)
        except Exception:
            return unicodedata.normalize("NFKC", value)
    return unicodedata.normalize("NFKC", value)


def _normalize_punctuation(value: str) -> str:
    return _PUNCTUATION_TO_SPACE.sub(" ", value)


def _normalize_volume_tokens(value: str) -> str:
    normalized = value
    normalized = re.sub(r"\b제?\s*0*(\d+)\s*권\b", r"\1권", normalized)
    normalized = re.sub(r"\b0*(\d+)\s*(권|편|부|화)\b", lambda m: f"{int(m.group(1))}권", normalized)

    def _replace_vol(match: re.Match) -> str:
        return f"{int(match.group(1))}권"

    def _replace_roman(match: re.Match) -> str:
        value = _roman_to_int(match.group(1))
        return f"{value}권" if value else match.group(0)

    normalized = re.sub(r"\b(?:vol(?:ume)?|v)\.?\s*0*(\d+)\b", _replace_vol, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(?:vol(?:ume)?|v)\.?\s*([ivxlcdm]+)\b", _replace_roman, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b([ivxlcdm]+)\s*(권|편|부|화)\b", _replace_roman, normalized, flags=re.IGNORECASE)
    return normalized


def _roman_to_int(text: str) -> int | None:
    roman = text.upper()
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(roman):
        if ch not in values:
            return None
        val = values[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    if total <= 0 or total > 3000:
        return None
    return total


def _load_replacements() -> list[tuple[object, str, bool]]:
    path = os.getenv("NORMALIZATION_RULES_PATH")
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []

    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, dict):
        return []

    replacements = rules.get("replacements", [])
    compiled: list[tuple[object, str, bool]] = []
    if not isinstance(replacements, list):
        return compiled

    for entry in replacements:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("pattern") or entry.get("from")
        replacement = entry.get("replacement") or entry.get("to") or ""
        if not pattern:
            continue
        is_regex = bool(entry.get("regex"))
        if is_regex:
            try:
                compiled.append((re.compile(pattern), str(replacement), True))
            except re.error:
                continue
        else:
            compiled.append((str(pattern), str(replacement), False))
    return compiled


def _ensure_rules_loaded() -> None:
    global _RULES_LOADED, _REPLACEMENTS
    if _RULES_LOADED:
        return
    _REPLACEMENTS = _load_replacements()
    _RULES_LOADED = True


def _apply_replacements(value: str) -> str:
    _ensure_rules_loaded()
    if not _REPLACEMENTS:
        return value
    updated = value
    for pattern, replacement, is_regex in _REPLACEMENTS:
        if is_regex:
            updated = pattern.sub(replacement, updated)
        else:
            updated = updated.replace(pattern, replacement)
    return updated


def reload_normalization_rules() -> None:
    global _RULES_LOADED
    _RULES_LOADED = False
