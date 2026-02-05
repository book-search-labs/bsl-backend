import re

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> dict:
    if not text:
        return {"detected": "unknown", "confidence": 0.0}
    hangul_count = len(_HANGUL.findall(text))
    latin_count = len(_LATIN.findall(text))
    total = hangul_count + latin_count
    if total == 0:
        return {"detected": "unknown", "confidence": 0.0}
    if hangul_count >= latin_count:
        confidence = hangul_count / total
        return {"detected": "ko", "confidence": round(confidence, 3)}
    confidence = latin_count / total
    return {"detected": "en", "confidence": round(confidence, 3)}
