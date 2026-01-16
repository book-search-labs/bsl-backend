import re
import unicodedata

CONTROL_WHITESPACE = {"\t", "\n", "\r", "\v", "\f"}


def normalize_query(raw: str) -> str:
    if raw is None:
        raise ValueError("missing_raw")
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = _strip_control_chars(normalized)
    normalized = normalized.strip()
    normalized = re.sub(r"\s+", " ", normalized)
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
