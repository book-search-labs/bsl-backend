from __future__ import annotations

import os
import re
from typing import Any, Tuple

import httpx

from app.core.metrics import metrics
from app.core.spell_candidates import get_generator


def _provider() -> str:
    return os.getenv("QS_SPELL_PROVIDER", "off").strip().lower()


def _spell_url() -> str:
    base = os.getenv("QS_SPELL_URL")
    if base:
        return base.rstrip("/")
    return os.getenv("QS_MIS_URL", "http://localhost:8005").rstrip("/")


def _spell_path() -> str:
    return os.getenv("QS_SPELL_PATH", "/v1/spell")


def _spell_timeout() -> float:
    return float(os.getenv("QS_SPELL_TIMEOUT_SEC", "2.0"))


def _spell_model() -> str:
    return os.getenv("QS_SPELL_MODEL", "toy-spell-v1")


def _len_ratio_bounds() -> Tuple[float, float]:
    min_ratio = float(os.getenv("QS_SPELL_LEN_RATIO_MIN", "0.6"))
    max_ratio = float(os.getenv("QS_SPELL_LEN_RATIO_MAX", "1.6"))
    return min_ratio, max_ratio


def _edit_distance_ratio_max() -> float:
    return float(os.getenv("QS_SPELL_EDIT_DISTANCE_RATIO_MAX", "0.4"))


def _max_length() -> int:
    return int(os.getenv("QS_SPELL_MAX_LEN", "128"))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _extract_numeric_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[0-9][0-9\-]{2,}", text or "")
    digits = [re.sub(r"[^0-9]", "", token) for token in tokens]
    return [token for token in digits if len(token) >= 4]


def _volume_numbers(text: str) -> set[str]:
    if not text:
        return set()
    numbers: set[str] = set()
    for match in re.finditer(r"\b(?:vol(?:ume)?|v)\.?\s*0*(\d+)\b", text, flags=re.IGNORECASE):
        if match.group(1):
            numbers.add(match.group(1))
    for match in re.finditer(r"\b0*(\d+)\s*(권|권차|vol(?:ume)?|v\.?)(?!\w)", text, flags=re.IGNORECASE):
        if match.group(1):
            numbers.add(match.group(1))
    return numbers


def _token_bag(text: str) -> list[str]:
    tokens = [token for token in re.split(r"\s+", text.lower().strip()) if token]
    return sorted(tokens)


def accept_spell_candidate(original: str, candidate: str) -> tuple[bool, str | None]:
    if not isinstance(candidate, str):
        return False, "empty"
    candidate = candidate.strip()
    if not candidate:
        return False, "empty"
    if any(not ch.isprintable() for ch in candidate):
        return False, "forbidden_char"

    if len(candidate) > _max_length():
        return False, "too_long"

    if candidate == original:
        return False, "no_change"

    normalized_original = _normalize(original)
    normalized_candidate = _normalize(candidate)
    if not normalized_original or not normalized_candidate:
        return False, "empty"

    min_ratio, max_ratio = _len_ratio_bounds()
    ratio = len(normalized_candidate) / max(len(normalized_original), 1)
    if ratio < min_ratio or ratio > max_ratio:
        return False, "length_ratio"

    numeric_tokens = _extract_numeric_tokens(original)
    if numeric_tokens:
        candidate_digits = re.sub(r"[^0-9]", "", candidate)
        for token in numeric_tokens:
            if token not in candidate_digits:
                return False, "numeric_mismatch"

    original_volumes = _volume_numbers(original)
    if original_volumes:
        candidate_volumes = _volume_numbers(candidate)
        if not original_volumes.issubset(candidate_volumes):
            return False, "volume_mismatch"

    if _token_bag(original) == _token_bag(candidate):
        return True, None

    distance = _edit_distance(normalized_original, normalized_candidate)
    if distance / max(len(normalized_original), 1) > _edit_distance_ratio_max():
        return False, "edit_distance"

    return True, None


def _mock_spell(text: str) -> tuple[str, float, str]:
    override = os.getenv("QS_SPELL_MOCK_RESPONSE")
    if override is not None:
        return override, 0.9, "mock"
    mapping = {
        "harry pottre": "harry potter",
        "haarry potter": "harry potter",
        "해리포터 1 권": "해리포터 1권",
    }
    lowered = text.lower()
    if lowered in mapping:
        return mapping[lowered], 0.9, "mock"
    return text, 0.0, "mock"


def _rule_spell(text: str) -> tuple[str, float, str]:
    return text, 0.0, "rule"


async def _call_spell_http(
    text: str,
    trace_id: str,
    request_id: str,
    locale: str,
) -> tuple[str, float, str, dict[str, Any]]:
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "text": text,
        "locale": locale,
        "model": _spell_model(),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_spell_url()}{_spell_path()}", json=payload, timeout=_spell_timeout())
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("invalid_spell_response")
    candidate = (
        data.get("corrected")
        or data.get("q_spell")
        or data.get("text")
        or data.get("result")
        or ""
    )
    confidence = float(data.get("confidence") or data.get("score") or 0.0)
    latency_ms = data.get("latency_ms")
    method = str(data.get("method") or data.get("model") or "http")
    model = data.get("model")
    meta = {"latency_ms": latency_ms, "model": model}
    return str(candidate), confidence, method, meta


def _default_payload(text: str) -> dict[str, Any]:
    return {
        "applied": False,
        "original": text,
        "corrected": text,
        "method": "none",
        "confidence": 0.0,
    }


async def run_spell(text: str, trace_id: str, request_id: str, locale: str) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = _provider()
    payload = _default_payload(text)
    meta: dict[str, Any] = {
        "provider": provider,
        "error_code": None,
        "error_message": None,
        "reject_reason": None,
        "candidates": None,
        "candidate_mode": None,
        "candidate_input": None,
        "provider_latency_ms": None,
        "provider_model": None,
    }

    if provider in {"off", "none"}:
        return payload, meta

    generator = get_generator()
    candidates = generator.generate(text) if generator else []
    if candidates:
        meta["candidates"] = [candidate.to_debug() for candidate in candidates]
        metrics.inc("qs_spell_candidate_total", value=len(candidates))
    candidate_mode = os.getenv("QS_SPELL_CANDIDATE_MODE", "hint").lower()
    meta["candidate_mode"] = candidate_mode
    request_text = text
    if candidate_mode in {"prefill", "best"} and candidates and provider in {"http", "rule", "mock"}:
        request_text = candidates[0].text
        meta["candidate_input"] = request_text

    metrics.inc("qs_spell_attempt_total", {"provider": provider})

    try:
        if provider == "mock":
            candidate, confidence, method = _mock_spell(request_text)
        elif provider == "rule":
            candidate, confidence, method = _rule_spell(request_text)
        else:
            candidate, confidence, method, extra = await _call_spell_http(
                request_text, trace_id, request_id, locale
            )
            meta["provider_latency_ms"] = extra.get("latency_ms")
            meta["provider_model"] = extra.get("model")
    except httpx.TimeoutException as exc:
        meta["error_code"] = "timeout"
        meta["error_message"] = str(exc)
        metrics.inc("qs_spell_rejected_total", {"provider": provider, "reason": "timeout"})
        return payload, meta
    except Exception as exc:
        meta["error_code"] = "provider_error"
        meta["error_message"] = str(exc)
        metrics.inc("qs_spell_rejected_total", {"provider": provider, "reason": "provider_error"})
        return payload, meta

    candidate = str(candidate)
    accepted, reject_reason = accept_spell_candidate(text, candidate)
    if not accepted:
        meta["reject_reason"] = reject_reason
        metrics.inc("qs_spell_rejected_total", {"provider": provider, "reason": str(reject_reason)})
        return payload, meta

    applied = candidate != text
    if applied:
        metrics.inc("qs_spell_applied_total", {"provider": provider})
    else:
        meta["reject_reason"] = "no_change"
        metrics.inc("qs_spell_rejected_total", {"provider": provider, "reason": "no_change"})

    payload = {
        "applied": applied,
        "original": text,
        "corrected": candidate if applied else text,
        "method": method,
        "confidence": float(confidence or 0.0),
    }
    return payload, meta
