from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, Tuple

import httpx

from app.core.metrics import metrics


def _provider() -> str:
    return os.getenv("QS_REWRITE_PROVIDER", "off").strip().lower()


def _rewrite_url() -> str:
    base = os.getenv("QS_REWRITE_URL")
    if base:
        return base.rstrip("/")
    return os.getenv("QS_LLM_URL", "http://localhost:8010").rstrip("/")


def _rewrite_path() -> str:
    return os.getenv("QS_REWRITE_PATH", "/v1/generate")


def _rewrite_timeout() -> float:
    return float(os.getenv("QS_REWRITE_TIMEOUT_SEC", "4.0"))


def _rewrite_model() -> str:
    return os.getenv("QS_REWRITE_MODEL", "toy-rewrite-v1")


def _rewrite_max_len() -> int:
    return int(os.getenv("QS_REWRITE_MAX_LEN", "128"))


def _mock_rewrite(text: str) -> tuple[str, float, str]:
    override = os.getenv("QS_REWRITE_MOCK_RESPONSE")
    if override is not None:
        return override, 0.7, "mock"
    mapping = {
        "hp": "harry potter",
        "해리 포터": "해리포터",
    }
    lowered = text.lower()
    if lowered in mapping:
        payload = {"q_rewrite": mapping[lowered], "confidence": 0.8}
        return json.dumps(payload, ensure_ascii=False), 0.8, "mock"
    payload = {"q_rewrite": text, "confidence": 0.0}
    return json.dumps(payload, ensure_ascii=False), 0.0, "mock"


def _default_payload(text: str) -> dict[str, Any]:
    return {
        "applied": False,
        "rewritten": text,
        "method": "none",
        "confidence": 0.0,
        "notes": "skipped",
    }


def _build_messages(text: str, reason: str | None, locale: str | None, candidates: Iterable[dict] | None) -> list[dict]:
    system = (
        "You are a query rewrite engine. Return ONLY a JSON object with keys: "
        "q_rewrite (string), confidence (number), intent (optional), slots (optional). "
        "Do not include explanations or extra text."
    )
    parts = [f"query: {text}"]
    if reason:
        parts.append(f"reason: {reason}")
    if locale:
        parts.append(f"locale: {locale}")
    if candidates:
        lines = []
        for idx, cand in enumerate(candidates, start=1):
            title = cand.get("title") or ""
            author = cand.get("author") or ""
            isbn = cand.get("isbn") or ""
            doc_id = cand.get("doc_id") or ""
            line = f"{idx}. {title}"
            details = ", ".join([val for val in [author, isbn, doc_id] if val])
            if details:
                line = f"{line} ({details})"
            lines.append(line)
        parts.append("candidates:\n" + "\n".join(lines))
    user = "\n".join(parts)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json(text: str | dict | None) -> dict[str, Any] | None:
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return None
    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = re.sub(r"^```(?:json)?", "", trimmed).strip()
        trimmed = re.sub(r"```$", "", trimmed).strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(trimmed[start : end + 1])
    except json.JSONDecodeError:
        return None


def _validate_rewrite(candidate: str, original: str) -> tuple[bool, str | None]:
    if not candidate or not candidate.strip():
        return False, "empty"
    if len(candidate) > _rewrite_max_len():
        return False, "too_long"
    if candidate.strip() == original.strip():
        return False, "no_change"
    if any(not ch.isprintable() for ch in candidate):
        return False, "forbidden_char"
    return True, None


async def _call_llm(
    text: str,
    trace_id: str,
    request_id: str,
    reason: str | None,
    locale: str | None,
    candidates: Iterable[dict] | None,
) -> tuple[str, float, str]:
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "model": _rewrite_model(),
        "messages": _build_messages(text, reason, locale, candidates),
        "citations_required": False,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_rewrite_url()}{_rewrite_path()}", json=payload, timeout=_rewrite_timeout())
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("invalid_rewrite_response")
    content = data.get("content") or ""
    return str(content), float(data.get("confidence") or 0.0), "llm"


async def run_rewrite(
    text: str,
    trace_id: str,
    request_id: str,
    reason: str | None,
    locale: str | None,
    candidates: Iterable[dict] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = _provider()
    payload = _default_payload(text)
    meta: dict[str, Any] = {
        "provider": provider,
        "error_code": None,
        "error_message": None,
        "reject_reason": None,
    }

    if provider in {"off", "none"}:
        meta["reject_reason"] = "provider_off"
        return payload, meta

    mode = "rag" if candidates else "plain"
    metrics.inc("qs_rewrite_attempt_total", {"provider": provider, "mode": mode})

    try:
        if provider == "mock":
            content, confidence, method = _mock_rewrite(text)
        else:
            content, confidence, method = await _call_llm(text, trace_id, request_id, reason, locale, candidates)
    except httpx.TimeoutException as exc:
        meta["error_code"] = "timeout"
        meta["error_message"] = str(exc)
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": "timeout"})
        return payload, meta
    except Exception as exc:
        meta["error_code"] = "provider_error"
        meta["error_message"] = str(exc)
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": "provider_error"})
        return payload, meta

    data = _extract_json(content)
    if data is None:
        meta["reject_reason"] = "invalid_json"
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": "invalid_json"})
        return payload, meta

    candidate = data.get("q_rewrite")
    if not isinstance(candidate, str):
        meta["reject_reason"] = "invalid_json"
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": "invalid_json"})
        return payload, meta

    candidate = candidate.strip()
    accepted, reject_reason = _validate_rewrite(candidate, text)
    if not accepted:
        meta["reject_reason"] = reject_reason
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": str(reject_reason)})
        return payload, meta

    applied = candidate != text
    if applied:
        metrics.inc("qs_rewrite_applied_total", {"provider": provider, "mode": mode})
    else:
        meta["reject_reason"] = "no_change"
        metrics.inc("qs_rewrite_failed_total", {"provider": provider, "reason": "no_change"})

    payload = {
        "applied": applied,
        "rewritten": candidate if applied else text,
        "method": method if candidates is None else f"{method}_rag",
        "confidence": float(data.get("confidence") or confidence or 0.0),
        "notes": str(data.get("intent") or "ok"),
    }
    return payload, meta
