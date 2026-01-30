import json
import os
import re
import unicodedata

CONTROL_WHITESPACE = {"\t", "\n", "\r", "\v", "\f"}
_RULES_LOADED = False
_REPLACEMENTS: list[tuple[object, str, bool]] = []


def normalize_query(raw: str) -> str:
    if raw is None:
        raise ValueError("missing_raw")
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = _strip_control_chars(normalized)
    normalized = normalized.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _apply_replacements(normalized)
    if normalized == "":
        raise ValueError("empty_query")
    return normalized


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
