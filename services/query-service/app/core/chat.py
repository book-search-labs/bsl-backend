import asyncio
from difflib import SequenceMatcher
import hashlib
import json
import os
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.analyzer import analyze_query
from app.core.cache import get_cache
from app.core.metrics import metrics
from app.core.chat_state_store import (
    append_action_audit,
    append_turn_event,
    get_session_state as get_durable_chat_session_state,
    upsert_session_state,
)
from app.core.chat_tools import get_recommend_experiment_snapshot, reset_ticket_session_context, run_tool_chat
from app.core.rag import retrieve_chunks_with_trace
from app.core.rag_candidates import retrieve_candidates
from app.core.rewrite import run_rewrite

_CACHE = get_cache()
_EPISODE_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", flags=re.IGNORECASE)
_EPISODE_PHONE_RE = re.compile(r"\b(?:\+?82[-\s]?)?0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b")
_EPISODE_PAYMENT_RE = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{3,4}\b")
_EPISODE_ADDRESS_RE = re.compile(
    r"(?:[가-힣A-Za-z0-9]+(?:시|도|군|구)\s+[가-힣A-Za-z0-9]+\s*(?:로|길)\s*\d+)",
    flags=re.IGNORECASE,
)
_EPISODE_ORDER_REF_RE = re.compile(r"\b(?:ORD\d{6,}|STK\d{6,}|\d{8,})\b", flags=re.IGNORECASE)


def _llm_provider_cooldown_sec() -> int:
    return max(0, int(os.getenv("QS_LLM_PROVIDER_COOLDOWN_SEC", "15")))


def _llm_provider_stats_ttl_sec() -> int:
    return max(300, int(os.getenv("QS_LLM_PROVIDER_STATS_TTL_SEC", "86400")))


def _llm_health_routing_enabled() -> bool:
    return str(os.getenv("QS_LLM_HEALTH_ROUTING_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _llm_health_min_sample() -> int:
    return max(1, int(os.getenv("QS_LLM_HEALTH_MIN_SAMPLE", "3")))


def _llm_health_streak_penalty_step() -> float:
    return max(0.0, float(os.getenv("QS_LLM_HEALTH_STREAK_PENALTY_STEP", "0.1")))


def _llm_health_streak_penalty_max() -> float:
    return min(0.95, max(0.0, float(os.getenv("QS_LLM_HEALTH_STREAK_PENALTY_MAX", "0.5"))))


def _llm_url() -> str:
    return os.getenv("QS_LLM_URL", "http://localhost:8010").rstrip("/")


def _llm_fallback_urls() -> List[str]:
    raw = os.getenv("QS_LLM_FALLBACK_URLS", "")
    urls = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    return [url for url in urls if url]


def _llm_provider_chain() -> List[tuple[str, str]]:
    providers: List[tuple[str, str]] = [("primary", _llm_url())]
    for idx, url in enumerate(_llm_fallback_urls(), start=1):
        if url and url != providers[0][1]:
            providers.append((f"fallback_{idx}", url))
    return providers


def _llm_forced_provider() -> str:
    return os.getenv("QS_LLM_FORCE_PROVIDER", "").strip()


def _llm_cost_steering_enabled() -> bool:
    return str(os.getenv("QS_LLM_COST_STEERING_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _llm_low_cost_provider() -> str:
    return os.getenv("QS_LLM_LOW_COST_PROVIDER", "").strip()


def _llm_provider_by_intent() -> Dict[str, str]:
    raw = os.getenv("QS_LLM_PROVIDER_BY_INTENT_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: Dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        intent = key.strip().upper()
        target = value.strip()
        if intent and target:
            result[intent] = target
    return result


def _extract_user_query_from_llm_payload(payload: Dict[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _apply_cost_steering(providers: List[tuple[str, str]], payload: Dict[str, Any], mode: str) -> List[tuple[str, str]]:
    if not _llm_cost_steering_enabled():
        return providers
    query = _extract_user_query_from_llm_payload(payload)
    if query and _is_high_risk_query(query):
        metrics.inc("chat_provider_cost_steer_total", {"provider": "none", "reason": "high_risk_bypass", "mode": mode})
        return providers
    target = _llm_low_cost_provider()
    if not target:
        metrics.inc("chat_provider_cost_steer_total", {"provider": "none", "reason": "not_configured", "mode": mode})
        return providers
    for idx, (name, url) in enumerate(providers):
        if target == name or target == url:
            metrics.inc("chat_provider_cost_steer_total", {"provider": name, "reason": "selected", "mode": mode})
            if idx == 0:
                return providers
            selected = providers[idx]
            return [selected] + [item for pos, item in enumerate(providers) if pos != idx]
    metrics.inc("chat_provider_cost_steer_total", {"provider": "unknown", "reason": "not_found", "mode": mode})
    return providers


def _query_intent(query: str) -> str:
    text = (query or "").lower()
    if not text:
        return "GENERAL"
    if any(keyword in text for keyword in ("환불", "취소", "refund", "cancel")):
        return "REFUND"
    if any(keyword in text for keyword in ("배송", "shipping", "tracking")):
        return "SHIPPING"
    if any(keyword in text for keyword in ("주문", "결제", "order", "payment")):
        return "ORDER"
    return "GENERAL"


def _apply_intent_routing(providers: List[tuple[str, str]], payload: Dict[str, Any], mode: str) -> List[tuple[str, str]]:
    query = _extract_user_query_from_llm_payload(payload)
    intent = _query_intent(query)
    policy = _llm_provider_by_intent()
    target = policy.get(intent)
    if not target:
        metrics.inc("chat_provider_intent_route_total", {"intent": intent, "provider": "none", "reason": "no_policy", "mode": mode})
        return providers
    for idx, (name, url) in enumerate(providers):
        if target == name or target == url:
            metrics.inc("chat_provider_intent_route_total", {"intent": intent, "provider": name, "reason": "selected", "mode": mode})
            if idx == 0:
                return providers
            selected = providers[idx]
            return [selected] + [item for pos, item in enumerate(providers) if pos != idx]
    metrics.inc("chat_provider_intent_route_total", {"intent": intent, "provider": target, "reason": "not_found", "mode": mode})
    return providers


def _provider_health_cache_key(provider: str) -> str:
    return f"chat:provider:cooldown:{provider}"


def _provider_stats_cache_key(provider: str) -> str:
    return f"chat:provider:stats:{provider}"


def _llm_provider_blocklist() -> set[str]:
    raw = os.getenv("QS_LLM_PROVIDER_BLOCKLIST", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _provider_matches_target(provider: tuple[str, str], target: str) -> bool:
    name, url = provider
    return target == name or target == url


def _is_forced_provider_blocked(all_providers: List[tuple[str, str]], filtered_providers: List[tuple[str, str]]) -> bool:
    forced = _llm_forced_provider()
    if not forced:
        return False
    in_all = any(_provider_matches_target(provider, forced) for provider in all_providers)
    if not in_all:
        return False
    in_filtered = any(_provider_matches_target(provider, forced) for provider in filtered_providers)
    return not in_filtered


def _provider_effective_score(provider: str) -> Optional[float]:
    raw = _CACHE.get_json(_provider_stats_cache_key(provider))
    if not isinstance(raw, dict):
        return None
    effective = raw.get("effective_score")
    if isinstance(effective, (int, float)):
        return min(1.0, max(0.0, float(effective)))
    ok = raw.get("ok")
    fail = raw.get("fail")
    streak_fail = raw.get("streak_fail")
    if not isinstance(ok, int) or not isinstance(fail, int):
        return None
    if not isinstance(streak_fail, int):
        streak_fail = 0
    if ok < 0 or fail < 0:
        return None
    total = ok + fail
    if total < _llm_health_min_sample():
        return None
    base_score = float(ok + 1) / float(total + 2)
    penalty = min(_llm_health_streak_penalty_max(), float(streak_fail) * _llm_health_streak_penalty_step())
    return max(0.0, base_score - penalty)


def _llm_provider_costs() -> Dict[str, float]:
    raw = os.getenv("QS_LLM_PROVIDER_COSTS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    costs: Dict[str, float] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            continue
        try:
            costs[key.strip()] = float(value)
        except Exception:
            continue
    return costs


def _record_provider_telemetry(provider: str, base_url: str, success: bool) -> None:
    cost_map = _llm_provider_costs()
    cost = cost_map.get(provider)
    if cost is None:
        cost = cost_map.get(base_url)
    if cost is not None:
        metrics.set("chat_provider_cost_per_1k", {"provider": provider}, value=float(cost))

    key = _provider_stats_cache_key(provider)
    raw = _CACHE.get_json(key)
    ok = 0
    fail = 0
    streak_fail = 0
    if isinstance(raw, dict):
        raw_ok = raw.get("ok")
        raw_fail = raw.get("fail")
        raw_streak = raw.get("streak_fail")
        if isinstance(raw_ok, int) and raw_ok >= 0:
            ok = raw_ok
        if isinstance(raw_fail, int) and raw_fail >= 0:
            fail = raw_fail
        if isinstance(raw_streak, int) and raw_streak >= 0:
            streak_fail = raw_streak
    if success:
        ok += 1
        streak_fail = 0
    else:
        fail += 1
        streak_fail += 1
    base_score = float(ok + 1) / float(ok + fail + 2)
    penalty = min(_llm_health_streak_penalty_max(), float(streak_fail) * _llm_health_streak_penalty_step())
    effective_score = max(0.0, base_score - penalty)
    _CACHE.set_json(
        key,
        {
            "ok": ok,
            "fail": fail,
            "streak_fail": streak_fail,
            "base_score": base_score,
            "effective_score": effective_score,
            "updated_at": int(time.time()),
        },
        ttl=_llm_provider_stats_ttl_sec(),
    )
    metrics.set("chat_provider_health_penalty", {"provider": provider}, value=penalty)
    metrics.set("chat_provider_health_score", {"provider": provider}, value=effective_score)


def _apply_provider_blocklist(providers: List[tuple[str, str]], mode: str) -> List[tuple[str, str]]:
    blocklist = _llm_provider_blocklist()
    if not blocklist:
        return providers
    kept: List[tuple[str, str]] = []
    blocked: List[tuple[str, str]] = []
    for name, url in providers:
        if name in blocklist or url in blocklist:
            metrics.inc("chat_provider_block_total", {"provider": name, "reason": "blocklist", "mode": mode})
            blocked.append((name, url))
            continue
        kept.append((name, url))
    # keep service available if all providers are blocked by mistake
    return kept or providers


def _mark_provider_unhealthy(provider: str, reason: str) -> None:
    ttl = _llm_provider_cooldown_sec()
    if ttl <= 0:
        return
    _CACHE.set_json(
        _provider_health_cache_key(provider),
        {"reason": reason, "updated_at": int(time.time())},
        ttl=ttl,
    )


def _clear_provider_unhealthy(provider: str) -> None:
    _CACHE.set_json(_provider_health_cache_key(provider), {"cleared": True}, ttl=1)


def _is_provider_unhealthy(provider: str) -> bool:
    if _llm_provider_cooldown_sec() <= 0:
        return False
    value = _CACHE.get_json(_provider_health_cache_key(provider))
    return isinstance(value, dict) and not bool(value.get("cleared"))


def _apply_provider_health(providers: List[tuple[str, str]], mode: str) -> List[tuple[str, str]]:
    if _llm_provider_cooldown_sec() <= 0:
        active = providers
    else:
        healthy: List[tuple[str, str]] = []
        unhealthy: List[tuple[str, str]] = []
        for provider in providers:
            name = provider[0]
            if _is_provider_unhealthy(name):
                metrics.inc("chat_provider_route_total", {"provider": name, "result": "cooldown_skip", "mode": mode})
                unhealthy.append(provider)
                continue
            healthy.append(provider)
        if not healthy:
            active = providers
        else:
            active = healthy + unhealthy
    if not _llm_health_routing_enabled():
        return active
    scored: List[tuple[float, int, tuple[str, str]]] = []
    for idx, provider in enumerate(active):
        name = provider[0]
        ratio = _provider_effective_score(name)
        # keep unknown providers at neutral score to avoid starvation.
        score = 0.5 if ratio is None else ratio
        scored.append((score, -idx, provider))
        metrics.set("chat_provider_health_score", {"provider": name}, value=score)
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored]


def _apply_provider_override(providers: List[tuple[str, str]], mode: str) -> List[tuple[str, str]]:
    forced = _llm_forced_provider()
    if not forced:
        return providers
    for idx, (name, url) in enumerate(providers):
        if forced == name or forced == url:
            metrics.inc("chat_provider_forced_route_total", {"provider": name, "reason": "selected", "mode": mode})
            if idx == 0:
                return providers
            selected = providers[idx]
            return [selected] + [item for pos, item in enumerate(providers) if pos != idx]
    metrics.inc("chat_provider_forced_route_total", {"provider": "unknown", "reason": "not_found", "mode": mode})
    return providers


def _move_provider_to_front(
    providers: List[tuple[str, str]],
    target: str,
) -> tuple[List[tuple[str, str]], Optional[str]]:
    for idx, provider in enumerate(providers):
        if _provider_matches_target(provider, target):
            if idx == 0:
                return providers, provider[0]
            selected = providers[idx]
            reordered = [selected] + [item for pos, item in enumerate(providers) if pos != idx]
            return reordered, selected[0]
    return providers, None


def _provider_stats_view(provider: str) -> Dict[str, Any]:
    raw = _CACHE.get_json(_provider_stats_cache_key(provider))
    if not isinstance(raw, dict):
        return {
            "ok": 0,
            "fail": 0,
            "streak_fail": 0,
            "base_score": None,
            "effective_score": None,
            "updated_at": None,
        }
    return {
        "ok": int(raw.get("ok")) if isinstance(raw.get("ok"), int) else 0,
        "fail": int(raw.get("fail")) if isinstance(raw.get("fail"), int) else 0,
        "streak_fail": int(raw.get("streak_fail")) if isinstance(raw.get("streak_fail"), int) else 0,
        "base_score": float(raw.get("base_score")) if isinstance(raw.get("base_score"), (int, float)) else None,
        "effective_score": float(raw.get("effective_score")) if isinstance(raw.get("effective_score"), (int, float)) else None,
        "updated_at": int(raw.get("updated_at")) if isinstance(raw.get("updated_at"), int) else None,
    }


def _preview_provider_routing(payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
    all_providers = _llm_provider_chain()
    blocklist = _llm_provider_blocklist()
    blocked: List[str] = []
    filtered: List[tuple[str, str]] = []
    for provider in all_providers:
        name, url = provider
        if name in blocklist or url in blocklist:
            blocked.append(name)
            continue
        filtered.append(provider)
    all_blocked_fallback = False
    providers = filtered
    if not providers:
        providers = list(all_providers)
        all_blocked_fallback = True

    forced_provider = _llm_forced_provider()
    forced_blocked = _is_forced_provider_blocked(all_providers, providers)
    query = _extract_user_query_from_llm_payload(payload)
    intent = _query_intent(query)
    intent_policy = _llm_provider_by_intent()
    intent_target = intent_policy.get(intent)
    intent_selected: Optional[str] = None
    if intent_target:
        providers, intent_selected = _move_provider_to_front(providers, intent_target)

    cost_target: Optional[str] = None
    cost_reason = "disabled"
    if _llm_cost_steering_enabled():
        if query and _is_high_risk_query(query):
            cost_reason = "high_risk_bypass"
        else:
            target = _llm_low_cost_provider()
            if not target:
                cost_reason = "not_configured"
            else:
                providers, cost_target = _move_provider_to_front(providers, target)
                cost_reason = "selected" if cost_target else "not_found"

    health_enabled = _llm_health_routing_enabled()
    health_scores: Dict[str, float] = {}
    if health_enabled:
        scored: List[tuple[float, int, tuple[str, str]]] = []
        for idx, provider in enumerate(providers):
            name = provider[0]
            score = _provider_effective_score(name)
            effective = 0.5 if score is None else float(score)
            scored.append((effective, -idx, provider))
            health_scores[name] = effective
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        providers = [item[2] for item in scored]

    forced_selected: Optional[str] = None
    if forced_provider and not forced_blocked:
        providers, forced_selected = _move_provider_to_front(providers, forced_provider)

    return {
        "mode": mode,
        "query_intent": intent,
        "forced_provider": forced_provider or None,
        "forced_blocked": forced_blocked,
        "forced_selected": forced_selected,
        "blocklist": sorted(blocklist),
        "blocked_providers": blocked,
        "all_blocked_fallback": all_blocked_fallback,
        "intent_policy_target": intent_target,
        "intent_policy_selected": intent_selected,
        "cost_steering_enabled": _llm_cost_steering_enabled(),
        "cost_target": _llm_low_cost_provider() or None,
        "cost_selected": cost_target,
        "cost_reason": cost_reason,
        "health_routing_enabled": health_enabled,
        "health_scores": health_scores,
        "final_chain": [name for name, _ in providers],
        "provider_stats": {name: _provider_stats_view(name) for name, _ in all_providers},
    }


def _llm_model() -> str:
    return os.getenv("QS_LLM_MODEL", "toy-rag-v1")


def _llm_timeout_sec() -> float:
    return float(os.getenv("QS_LLM_TIMEOUT_SEC", "10.0"))


def _llm_max_provider_attempts_per_turn() -> int:
    return max(1, int(os.getenv("QS_CHAT_MAX_PROVIDER_ATTEMPTS_PER_TURN", "2")))


def _llm_max_prompt_tokens_per_turn() -> int:
    return max(64, int(os.getenv("QS_CHAT_MAX_PROMPT_TOKENS_PER_TURN", "6000")))


def _llm_max_completion_tokens_per_turn() -> int:
    return max(32, int(os.getenv("QS_CHAT_MAX_COMPLETION_TOKENS_PER_TURN", "1200")))


def _llm_max_total_tokens_per_turn() -> int:
    default_total = _llm_max_prompt_tokens_per_turn() + _llm_max_completion_tokens_per_turn()
    return max(96, int(os.getenv("QS_CHAT_MAX_TOTAL_TOKENS_PER_TURN", str(default_total))))


def _llm_max_calls_per_minute() -> int:
    return max(0, int(os.getenv("QS_CHAT_MAX_LLM_CALLS_PER_MINUTE", "0")))


def _estimate_token_count(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, len(normalized) // 4)


def _estimate_prompt_tokens(payload: Dict[str, Any]) -> int:
    total = 0
    messages = payload.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, dict):
                continue
            total += _estimate_token_count(str(item.get("content") or ""))
    context = payload.get("context")
    chunks = context.get("chunks") if isinstance(context, dict) else []
    if isinstance(chunks, list):
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            total += _estimate_token_count(str(chunk.get("content") or ""))
            total += _estimate_token_count(str(chunk.get("title") or ""))
    return total


def _requested_completion_tokens(payload: Dict[str, Any]) -> int:
    raw = payload.get("max_tokens")
    if isinstance(raw, (int, float)):
        return max(1, int(raw))
    return _llm_max_completion_tokens_per_turn()


def _admission_block_reason(payload: Dict[str, Any], *, mode: str = "unknown") -> Optional[str]:
    prompt_tokens = _estimate_prompt_tokens(payload)
    completion_tokens = _requested_completion_tokens(payload)
    total_tokens = prompt_tokens + completion_tokens
    max_prompt = _llm_max_prompt_tokens_per_turn()
    max_completion = _llm_max_completion_tokens_per_turn()
    max_total = _llm_max_total_tokens_per_turn()

    metrics.set("chat_llm_prompt_tokens_estimate", {"mode": mode}, value=float(prompt_tokens))
    metrics.set("chat_llm_completion_tokens_estimate", {"mode": mode}, value=float(completion_tokens))
    metrics.set("chat_llm_total_tokens_estimate", {"mode": mode}, value=float(total_tokens))
    metrics.set(
        "chat_llm_token_budget_utilization",
        {"mode": mode, "budget": "prompt"},
        value=float(prompt_tokens) / float(max(1, max_prompt)),
    )
    metrics.set(
        "chat_llm_token_budget_utilization",
        {"mode": mode, "budget": "completion"},
        value=float(completion_tokens) / float(max(1, max_completion)),
    )
    metrics.set(
        "chat_llm_token_budget_utilization",
        {"mode": mode, "budget": "total"},
        value=float(total_tokens) / float(max(1, max_total)),
    )

    if prompt_tokens > max_prompt:
        return "LLM_PROMPT_BUDGET_EXCEEDED"
    if completion_tokens > max_completion:
        return "LLM_COMPLETION_BUDGET_EXCEEDED"
    if total_tokens > max_total:
        return "LLM_TOTAL_BUDGET_EXCEEDED"
    return None


def _llm_call_rate_cache_key(session_id: Optional[str], user_id: Optional[str]) -> str:
    if isinstance(user_id, str) and user_id.strip():
        return f"chat:llm:call_rate:user:{user_id.strip()}"
    if isinstance(session_id, str) and session_id.strip():
        return f"chat:llm:call_rate:session:{session_id.strip()}"
    return "chat:llm:call_rate:anon"


def _llm_call_rate_cache_keys(session_id: Optional[str], user_id: Optional[str]) -> List[str]:
    keys: List[str] = []
    if isinstance(user_id, str) and user_id.strip():
        keys.append(_llm_call_rate_cache_key(None, user_id.strip()))
    if isinstance(session_id, str) and session_id.strip():
        keys.append(_llm_call_rate_cache_key(session_id.strip(), None))
    if not keys:
        keys.append(_llm_call_rate_cache_key(None, None))
    deduped: List[str] = []
    for key in keys:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _load_llm_call_budget_count(session_id: Optional[str], user_id: Optional[str]) -> int:
    max_count = 0
    for key in _llm_call_rate_cache_keys(session_id, user_id):
        cached = _CACHE.get_json(key)
        if not isinstance(cached, dict):
            continue
        count = int(cached.get("count") or 0)
        if count > max_count:
            max_count = count
    return max(0, max_count)


def _load_llm_call_budget_snapshot(session_id: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    limit = _llm_max_calls_per_minute()
    best_count = 0
    best_window_start = 0
    for key in _llm_call_rate_cache_keys(session_id, user_id):
        cached = _CACHE.get_json(key)
        if not isinstance(cached, dict):
            continue
        count = max(0, int(cached.get("count") or 0))
        window_start = max(0, int(cached.get("window_start") or 0))
        if count > best_count or (count == best_count and window_start > best_window_start):
            best_count = count
            best_window_start = window_start
    return {
        "count": best_count,
        "limit": limit,
        "limited": bool(limit > 0 and best_count >= limit),
        "window_sec": 60,
        "window_start": best_window_start if best_window_start > 0 else None,
    }


def _clear_llm_call_budget(session_id: Optional[str], user_id: Optional[str]) -> None:
    now_ts = int(time.time())
    for key in _llm_call_rate_cache_keys(session_id, user_id):
        _CACHE.set_json(key, {"count": 0, "window_start": now_ts, "updated_at": now_ts}, ttl=5)


def _reserve_llm_call_budget(session_id: Optional[str], user_id: Optional[str], *, mode: str) -> Optional[str]:
    limit = _llm_max_calls_per_minute()
    if limit <= 0:
        return None
    now_ts = int(time.time())
    cache_key = _llm_call_rate_cache_key(session_id, user_id)
    cached = _CACHE.get_json(cache_key)
    window_start = now_ts
    count = 0
    if isinstance(cached, dict):
        window_start = int(cached.get("window_start") or now_ts)
        count = max(0, int(cached.get("count") or 0))
    if now_ts - window_start >= 60:
        window_start = now_ts
        count = 0
    if count >= limit:
        metrics.inc("chat_llm_call_budget_total", {"mode": mode, "result": "blocked"})
        return "LLM_CALL_RATE_LIMITED"
    count += 1
    _CACHE.set_json(
        cache_key,
        {
            "window_start": window_start,
            "count": count,
            "limit": limit,
            "updated_at": now_ts,
        },
        ttl=120,
    )
    metrics.inc("chat_llm_call_budget_total", {"mode": mode, "result": "allow"})
    metrics.set("chat_llm_call_rate_utilization", {"mode": mode}, value=float(count) / float(max(1, limit)))
    return None


def _chat_engine_mode() -> str:
    raw = os.getenv("QS_CHAT_ENGINE_MODE", "agent").strip().lower()
    if raw in {"legacy", "agent", "canary", "shadow"}:
        return raw
    return "agent"


def _chat_engine_canary_percent() -> int:
    return min(100, max(0, int(os.getenv("QS_CHAT_ENGINE_CANARY_PERCENT", "5"))))


def _chat_rollout_gate_window_sec() -> int:
    return max(30, int(os.getenv("QS_CHAT_ROLLOUT_GATE_WINDOW_SEC", "300")))


def _chat_rollout_gate_min_samples() -> int:
    return max(1, int(os.getenv("QS_CHAT_ROLLOUT_GATE_MIN_SAMPLES", "20")))


def _chat_rollout_gate_fail_ratio_threshold() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_ROLLOUT_GATE_FAIL_RATIO_THRESHOLD", "0.2"))))


def _chat_rollout_rollback_cooldown_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_ROLLOUT_ROLLBACK_COOLDOWN_SEC", "60")))


def _chat_rollout_auto_rollback_enabled() -> bool:
    return str(os.getenv("QS_CHAT_ROLLOUT_AUTO_ROLLBACK_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _chat_rollout_rollback_cache_key() -> str:
    return "chat:rollout:rollback"


def _chat_rollout_gate_cache_key(engine: str) -> str:
    return f"chat:rollout:gate:{engine}"


def _chat_engine_bucket(request: Dict[str, Any], request_id: str) -> int:
    session_id = request.get("session_id") if isinstance(request.get("session_id"), str) else ""
    user_id = _extract_user_id(request) or ""
    seed = f"{session_id}:{user_id}:{request_id}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _get_active_rollout_rollback() -> Optional[Dict[str, Any]]:
    cached = _CACHE.get_json(_chat_rollout_rollback_cache_key())
    if not isinstance(cached, dict):
        return None
    until = int(cached.get("until_ts") or 0)
    now_ts = int(time.time())
    if until <= now_ts:
        return None
    return {
        "until_ts": until,
        "reason": str(cached.get("reason") or "unknown"),
        "fail_ratio": float(cached.get("fail_ratio") or 0.0),
    }


def _set_rollout_rollback(reason: str, fail_ratio: float, total: int, failures: int) -> None:
    cooldown = _chat_rollout_rollback_cooldown_sec()
    until_ts = int(time.time()) + cooldown
    event_request_id = f"rollout-rollback-{int(time.time() * 1000)}"
    _CACHE.set_json(
        _chat_rollout_rollback_cache_key(),
        {
            "until_ts": until_ts,
            "reason": reason,
            "fail_ratio": float(fail_ratio),
            "total": int(total),
            "failures": int(failures),
            "updated_at": int(time.time()),
        },
        ttl=cooldown,
    )
    append_action_audit(
        conversation_id="rollout:chat",
        action_type="CHAT_ENGINE_ROLLBACK",
        action_state="EXECUTED",
        decision="ALLOW",
        result="SUCCESS",
        actor_user_id=None,
        actor_admin_id="system",
        target_ref="chat.engine",
        auth_context={"mode": _chat_engine_mode(), "source": "auto_gate"},
        trace_id="rollout",
        request_id=event_request_id,
        reason_code=reason,
        idempotency_key=event_request_id,
        metadata={"fail_ratio": fail_ratio, "total": total, "failures": failures, "until_ts": until_ts},
    )
    metrics.inc("chat_rollout_rollback_total", {"reason": reason})


def _select_rollout_engine(request: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    mode = _chat_engine_mode()
    rollback = _get_active_rollout_rollback()
    if rollback is not None:
        metrics.inc("chat_rollout_traffic_ratio", {"engine": "legacy"})
        return {
            "mode": mode,
            "effective_engine": "legacy",
            "shadow_enabled": False,
            "reason": "auto_rollback",
            "rollback": rollback,
        }

    if mode == "legacy":
        metrics.inc("chat_rollout_traffic_ratio", {"engine": "legacy"})
        return {"mode": mode, "effective_engine": "legacy", "shadow_enabled": False, "reason": "fixed"}
    if mode == "agent":
        metrics.inc("chat_rollout_traffic_ratio", {"engine": "agent"})
        return {"mode": mode, "effective_engine": "agent", "shadow_enabled": False, "reason": "fixed"}
    if mode == "canary":
        bucket = _chat_engine_bucket(request, request_id)
        threshold = _chat_engine_canary_percent()
        engine = "agent" if bucket < threshold else "legacy"
        metrics.inc("chat_rollout_traffic_ratio", {"engine": engine})
        return {
            "mode": mode,
            "effective_engine": engine,
            "shadow_enabled": False,
            "reason": "canary",
            "bucket": bucket,
            "threshold": threshold,
        }
    # shadow mode: primary legacy, secondary simulated agent compare
    metrics.inc("chat_rollout_traffic_ratio", {"engine": "legacy"})
    return {"mode": "shadow", "effective_engine": "legacy", "shadow_enabled": True, "reason": "shadow"}


def _is_rollout_failure(response: Dict[str, Any]) -> bool:
    status = str(response.get("status") or "").strip().lower()
    reason = str(response.get("reason_code") or "").strip().upper()
    if status in {"error"}:
        return True
    failure_reasons = {
        "PROVIDER_TIMEOUT",
        "TOOL_UNAVAILABLE",
        "LLM_NO_CITATIONS",
        "LLM_LOW_CITATION_COVERAGE",
        "OUTPUT_GUARD_FORBIDDEN_CLAIM",
        "DENY_CLAIM:NO_TOOL_RESULT",
    }
    return reason in failure_reasons


def _record_rollout_gate(engine: str, response: Dict[str, Any]) -> None:
    if engine != "agent":
        return
    if not _chat_rollout_auto_rollback_enabled():
        return
    gate_key = _chat_rollout_gate_cache_key(engine)
    now_ts = int(time.time())
    raw = _CACHE.get_json(gate_key)
    window_start = now_ts
    total = 0
    failures = 0
    if isinstance(raw, dict):
        window_start = int(raw.get("window_start") or now_ts)
        total = int(raw.get("total") or 0)
        failures = int(raw.get("failures") or 0)
    if now_ts - window_start > _chat_rollout_gate_window_sec():
        window_start = now_ts
        total = 0
        failures = 0
    total += 1
    if _is_rollout_failure(response):
        failures += 1
    fail_ratio = float(failures) / float(max(1, total))
    _CACHE.set_json(
        gate_key,
        {
            "window_start": window_start,
            "total": total,
            "failures": failures,
            "fail_ratio": fail_ratio,
            "updated_at": now_ts,
        },
        ttl=max(_chat_rollout_gate_window_sec() * 2, 120),
    )
    metrics.set("chat_rollout_failure_ratio", {"engine": engine}, value=fail_ratio)
    gate_result = "pass"
    if total >= _chat_rollout_gate_min_samples() and fail_ratio > _chat_rollout_gate_fail_ratio_threshold():
        gate_result = "rollback"
        _set_rollout_rollback("gate_failure_ratio", fail_ratio, total, failures)
    metrics.inc("chat_rollout_gate_total", {"engine": engine, "result": gate_result})


def _rollout_gate_snapshot(engine: str) -> Dict[str, Any]:
    raw = _CACHE.get_json(_chat_rollout_gate_cache_key(engine))
    if not isinstance(raw, dict):
        return {
            "engine": engine,
            "window_start": None,
            "total": 0,
            "failures": 0,
            "fail_ratio": 0.0,
            "updated_at": None,
        }
    return {
        "engine": engine,
        "window_start": int(raw.get("window_start") or 0) or None,
        "total": max(0, int(raw.get("total") or 0)),
        "failures": max(0, int(raw.get("failures") or 0)),
        "fail_ratio": max(0.0, float(raw.get("fail_ratio") or 0.0)),
        "updated_at": int(raw.get("updated_at") or 0) or None,
    }


def get_chat_rollout_snapshot(trace_id: str, request_id: str) -> Dict[str, Any]:
    return {
        "mode": _chat_engine_mode(),
        "canary_percent": _chat_engine_canary_percent(),
        "auto_rollback_enabled": _chat_rollout_auto_rollback_enabled(),
        "gate_window_sec": _chat_rollout_gate_window_sec(),
        "gate_min_samples": _chat_rollout_gate_min_samples(),
        "gate_fail_ratio_threshold": _chat_rollout_gate_fail_ratio_threshold(),
        "rollback_cooldown_sec": _chat_rollout_rollback_cooldown_sec(),
        "active_rollback": _get_active_rollout_rollback(),
        "gates": {
            "agent": _rollout_gate_snapshot("agent"),
            "legacy": _rollout_gate_snapshot("legacy"),
        },
        "trace_id": trace_id,
        "request_id": request_id,
    }


def reset_chat_rollout_state(
    trace_id: str,
    request_id: str,
    *,
    clear_gate: bool = True,
    clear_rollback: bool = True,
    engine: Optional[str] = None,
    actor_admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_engine = str(engine or "").strip().lower() or None
    if normalized_engine not in {None, "agent", "legacy"}:
        raise ValueError("invalid_engine")
    before = get_chat_rollout_snapshot(trace_id, request_id)

    cleared_engines: List[str] = []
    if clear_gate:
        targets = [normalized_engine] if normalized_engine else ["agent", "legacy"]
        for target in targets:
            if target is None:
                continue
            _CACHE.set_json(_chat_rollout_gate_cache_key(target), {"cleared": True}, ttl=1)
            cleared_engines.append(target)
    if clear_rollback:
        _CACHE.set_json(_chat_rollout_rollback_cache_key(), {"cleared": True}, ttl=1)

    after = get_chat_rollout_snapshot(trace_id, request_id)
    reset_at_ms = int(time.time() * 1000)
    append_action_audit(
        conversation_id="rollout:chat",
        action_type="CHAT_ROLLOUT_RESET",
        action_state="EXECUTED",
        decision="ALLOW",
        result="SUCCESS",
        actor_user_id=None,
        actor_admin_id=actor_admin_id,
        target_ref="chat.engine",
        auth_context={"mode": _chat_engine_mode(), "source": "manual"},
        trace_id=trace_id,
        request_id=request_id,
        reason_code="MANUAL_RESET",
        idempotency_key=f"rollout-reset:{request_id}",
        metadata={
            "clear_gate": clear_gate,
            "clear_rollback": clear_rollback,
            "engine": normalized_engine,
            "cleared_gate_engines": cleared_engines,
            "reset_at_ms": reset_at_ms,
        },
    )
    metrics.inc("chat_rollout_reset_total", {"result": "ok"})
    return {
        "reset_applied": True,
        "reset_at_ms": reset_at_ms,
        "before": before,
        "after": after,
        "options": {
            "clear_gate": clear_gate,
            "clear_rollback": clear_rollback,
            "engine": normalized_engine,
            "cleared_gate_engines": cleared_engines,
        },
    }


async def _shadow_agent_signature(request: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, str]:
    validation_reason = _validate_chat_request(request)
    if validation_reason:
        return {"status": "fallback", "reason_code": validation_reason}
    prepared = await _prepare_chat(request, trace_id, request_id, session_id=None, user_id=None)
    if not prepared.get("ok"):
        response = prepared.get("response") if isinstance(prepared.get("response"), dict) else {}
        reason_code = str(response.get("reason_code") or str(prepared.get("reason") or "RAG_NO_CHUNKS"))
        return {"status": "fallback", "reason_code": reason_code}
    payload = _build_llm_payload(
        request,
        trace_id,
        request_id,
        str(prepared.get("query") or ""),
        list(prepared.get("selected") or []),
    )
    admission_reason = _admission_block_reason(payload, mode="shadow")
    if admission_reason:
        return {"status": "fallback", "reason_code": admission_reason}
    return {"status": "ok", "reason_code": "SHADOW_SIMULATED_OK"}


def _record_shadow_diff(primary_response: Dict[str, Any], shadow_signature: Dict[str, str]) -> None:
    primary_status = "ok" if str(primary_response.get("status") or "").lower() == "ok" else "fallback"
    primary_reason = str(primary_response.get("reason_code") or "")
    shadow_status = str(shadow_signature.get("status") or "fallback")
    shadow_reason = str(shadow_signature.get("reason_code") or "UNKNOWN")
    if primary_status == shadow_status:
        metrics.inc("chat_rollout_shadow_diff_total", {"result": "match"})
    else:
        metrics.inc("chat_rollout_shadow_diff_total", {"result": "diff"})
    if primary_reason == shadow_reason:
        metrics.inc("chat_rollout_shadow_reason_total", {"result": "match"})
    else:
        metrics.inc("chat_rollout_shadow_reason_total", {"result": "diff"})


def _llm_stream_enabled() -> bool:
    return str(os.getenv("QS_LLM_STREAM_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _is_failover_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _rewrite_on_bad_enabled() -> bool:
    return str(os.getenv("QS_CHAT_REWRITE_ON_BAD", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _retrieval_cache_ttl_sec() -> int:
    return int(os.getenv("QS_RAG_RETRIEVAL_CACHE_TTL_SEC", "180"))


def _answer_cache_ttl_sec() -> int:
    return int(os.getenv("QS_RAG_ANSWER_CACHE_TTL_SEC", "120"))


def _answer_cache_enabled() -> bool:
    return str(os.getenv("QS_RAG_ANSWER_CACHE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _semantic_cache_enabled() -> bool:
    return str(os.getenv("QS_CHAT_SEMANTIC_CACHE_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _semantic_cache_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_SEMANTIC_CACHE_TTL_SEC", "300")))


def _semantic_cache_similarity_threshold() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_SEMANTIC_CACHE_SIMILARITY_THRESHOLD", "0.82"))))


def _semantic_cache_max_candidates() -> int:
    return max(1, int(os.getenv("QS_CHAT_SEMANTIC_CACHE_MAX_CANDIDATES", "20")))


def _semantic_cache_drift_min_samples() -> int:
    return max(1, int(os.getenv("QS_CHAT_SEMANTIC_CACHE_DRIFT_MIN_SAMPLES", "20")))


def _semantic_cache_drift_max_error_rate() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_SEMANTIC_CACHE_DRIFT_MAX_ERROR_RATE", "0.2"))))


def _semantic_cache_auto_disable_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_SEMANTIC_CACHE_AUTO_DISABLE_SEC", "300")))


def _bad_score_threshold() -> float:
    return float(os.getenv("QS_RAG_BAD_SCORE_THRESHOLD", "0.03"))


def _min_diversity_ratio() -> float:
    return float(os.getenv("QS_RAG_MIN_DIVERSITY_RATIO", "0.4"))


def _prompt_version() -> str:
    return os.getenv("QS_CHAT_PROMPT_VERSION", "v1")


def _output_guard_enabled() -> bool:
    return str(os.getenv("QS_CHAT_OUTPUT_GUARD_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _guard_high_risk_min_citations() -> int:
    return max(1, int(os.getenv("QS_CHAT_GUARD_HIGH_RISK_MIN_CITATIONS", "1")))


def _risk_band_high_keywords() -> List[str]:
    raw = os.getenv(
        "QS_CHAT_RISK_HIGH_KEYWORDS",
        "주문,결제,환불,취소,배송,주소,payment,refund,cancel,shipping,address",
    )
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _guard_forbidden_answer_keywords() -> List[str]:
    raw = os.getenv(
        "QS_CHAT_GUARD_FORBIDDEN_ANSWER_KEYWORDS",
        "무조건,반드시,절대,100% 보장,guarantee,always",
    )
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _chat_min_citation_coverage_ratio() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_MIN_CITATION_COVERAGE_RATIO", "0.2"))))


def _chat_high_risk_min_citation_coverage_ratio() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_HIGH_RISK_MIN_CITATION_COVERAGE_RATIO", "0.5"))))


def _record_chat_timeout(stage: str) -> None:
    metrics.inc("chat_timeout_total", {"stage": stage})


def _chat_max_message_chars() -> int:
    return max(100, int(os.getenv("QS_CHAT_MAX_MESSAGE_CHARS", "1200")))


def _chat_max_history_turns() -> int:
    return max(1, int(os.getenv("QS_CHAT_MAX_HISTORY_TURNS", "12")))


def _chat_max_total_chars() -> int:
    return max(_chat_max_message_chars(), int(os.getenv("QS_CHAT_MAX_TOTAL_CHARS", "6000")))


def _chat_max_top_k() -> int:
    return max(1, int(os.getenv("QS_CHAT_MAX_TOP_K", "20")))


def _chat_session_id_max_len() -> int:
    return max(16, int(os.getenv("QS_CHAT_SESSION_ID_MAX_LEN", "64")))


def _chat_session_id_pattern() -> re.Pattern[str]:
    return re.compile(os.getenv("QS_CHAT_SESSION_ID_PATTERN", r"^[A-Za-z0-9:_-]+$"))


def _unresolved_context_ttl_sec() -> int:
    return max(300, int(os.getenv("QS_CHAT_UNRESOLVED_CONTEXT_TTL_SEC", "1800")))


def _episode_memory_enabled() -> bool:
    return str(os.getenv("QS_CHAT_EPISODE_MEMORY_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _episode_memory_default_opt_in() -> bool:
    return str(os.getenv("QS_CHAT_EPISODE_MEMORY_DEFAULT_OPT_IN", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _episode_memory_ttl_sec() -> int:
    return max(300, int(os.getenv("QS_CHAT_EPISODE_MEMORY_TTL_SEC", "2592000")))


def _episode_memory_max_items() -> int:
    return max(1, int(os.getenv("QS_CHAT_EPISODE_MEMORY_MAX_ITEMS", "5")))


def _episode_memory_prompt_items() -> int:
    return max(1, int(os.getenv("QS_CHAT_EPISODE_MEMORY_PROMPT_ITEMS", "3")))


def _episode_memory_max_fact_len() -> int:
    return max(20, int(os.getenv("QS_CHAT_EPISODE_MEMORY_MAX_FACT_LEN", "120")))


def _extract_citations_from_text(text: str) -> List[str]:
    matches = re.findall(r"\[([a-zA-Z0-9_\-:#]+)\]", text or "")
    seen: set[str] = set()
    ordered: List[str] = []
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        ordered.append(match)
    return ordered


def _normalize_query(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _semantic_cache_disable_key() -> str:
    return "rag:sem:disable"


def _semantic_cache_drift_key() -> str:
    return "rag:sem:drift"


def _semantic_cache_policy_version() -> str:
    raw = str(os.getenv("QS_CHAT_POLICY_TOPIC_VERSION", "v1")).strip()
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)
    return sanitized or "v1"


def _semantic_cache_topic_key(topic: str, locale: str) -> str:
    normalized_topic = _normalize_query(topic).replace(" ", "_") or "generic"
    normalized_locale = (locale or "ko-KR").strip() or "ko-KR"
    return f"rag:sem:{normalized_topic}:{normalized_locale}:{_semantic_cache_policy_version()}:{_prompt_version()}"


def _semantic_cache_similarity(a: str, b: str) -> float:
    left = _normalize_query(a)
    right = _normalize_query(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = {token for token in left.split(" ") if token}
    right_tokens = {token for token in right.split(" ") if token}
    jaccard = 0.0
    union = left_tokens | right_tokens
    if union:
        jaccard = float(len(left_tokens & right_tokens)) / float(len(union))
    ratio = SequenceMatcher(None, left, right).ratio()
    return max(jaccard, ratio)


def _semantic_cache_topic_classify(query: str) -> tuple[Optional[str], str]:
    normalized = _normalize_query(query)
    if not normalized:
        return None, "EMPTY_QUERY"
    policy_keywords = ["정책", "조건", "정리", "안내", "절차", "규정", "기준", "수수료", "가능", "policy", "guide"]
    if not any(keyword in normalized for keyword in policy_keywords):
        return None, "LANE_NOT_ALLOWED"
    if re.search(r"\bord\d{6,}\b", normalized, flags=re.IGNORECASE):
        return None, "LOOKUP_REFERENCE_DETECTED"
    if re.search(r"\b\d{4,}\b", normalized):
        return None, "LOOKUP_REFERENCE_DETECTED"
    if any(keyword in normalized for keyword in ["조회", "상태", "tracking", "lookup", "내역"]):
        return None, "LOOKUP_LANE_BLOCKED"
    has_refund_keyword = any(keyword in normalized for keyword in ["환불", "반품", "refund", "return"])
    if has_refund_keyword and any(
        keyword in normalized
        for keyword in ["전자책", "ebook", "e-book", "digital", "epub", "pdf", "다운로드"]
    ):
        return "EbookRefundPolicy", "CLASSIFIED"
    if has_refund_keyword:
        return "RefundPolicy", "CLASSIFIED"
    if any(keyword in normalized for keyword in ["배송", "택배", "출고", "shipping", "shipment", "delivery"]):
        return "ShippingPolicy", "CLASSIFIED"
    if any(keyword in normalized for keyword in ["주문 취소", "취소", "cancel", "cancellation"]):
        return "OrderCancelPolicy", "CLASSIFIED"
    if any(keyword in normalized for keyword in ["주문", "결제", "order", "payment"]):
        return "OrderPolicy", "CLASSIFIED"
    return None, "TOPIC_UNCLASSIFIED"


def _semantic_cache_topic_for_query(query: str) -> Optional[str]:
    topic, _ = _semantic_cache_topic_classify(query)
    return topic


def _semantic_cache_claim_safe(answer_text: str, citations: List[str]) -> tuple[bool, str]:
    answer = (answer_text or "").strip()
    if not answer:
        return False, "EMPTY_ANSWER"
    if not citations:
        return False, "NO_CITATIONS"
    if _contains_forbidden_claim(answer):
        return False, "FORBIDDEN_CLAIM"
    return True, "OK"


def _semantic_cache_auto_disabled_reason() -> Optional[str]:
    cached = _CACHE.get_json(_semantic_cache_disable_key())
    if not isinstance(cached, dict):
        return None
    until_ts = int(cached.get("until_ts") or 0)
    if until_ts <= int(time.time()):
        return None
    return str(cached.get("reason") or "AUTO_DISABLED")


def _semantic_cache_record_quality(*, ok: bool, reason: str) -> None:
    state = _CACHE.get_json(_semantic_cache_drift_key())
    total = 0
    errors = 0
    if isinstance(state, dict):
        total = max(0, int(state.get("total") or 0))
        errors = max(0, int(state.get("errors") or 0))
    total += 1
    if not ok:
        errors += 1
    error_rate = float(errors) / float(max(1, total))
    _CACHE.set_json(
        _semantic_cache_drift_key(),
        {"total": total, "errors": errors, "error_rate": error_rate, "updated_at": int(time.time())},
        ttl=max(_semantic_cache_auto_disable_sec() * 4, 1800),
    )
    if total >= _semantic_cache_drift_min_samples() and error_rate > _semantic_cache_drift_max_error_rate():
        until_ts = int(time.time()) + _semantic_cache_auto_disable_sec()
        _CACHE.set_json(
            _semantic_cache_disable_key(),
            {"until_ts": until_ts, "reason": "DRIFT_AUTO_DISABLED", "error_rate": error_rate},
            ttl=_semantic_cache_auto_disable_sec(),
        )
        metrics.inc("chat_semantic_cache_auto_disable_total", {"reason": "drift"})
        metrics.inc("chat_semantic_cache_block_total", {"reason": "AUTO_DISABLED"})
    metrics.inc("chat_semantic_cache_quality_total", {"result": "ok" if ok else "error", "reason": reason})


def _semantic_cache_rebind_response(response: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    rebound = dict(response)
    rebound["trace_id"] = trace_id
    rebound["request_id"] = request_id
    return rebound


def _semantic_cache_lookup(query: str, locale: str, trace_id: str, request_id: str) -> Optional[Dict[str, Any]]:
    if not _semantic_cache_enabled():
        return None
    disable_reason = _semantic_cache_auto_disabled_reason()
    if disable_reason:
        metrics.inc("chat_semantic_cache_block_total", {"reason": disable_reason})
        metrics.inc("chat_policy_topic_miss_total", {"reason": disable_reason})
        return None
    topic, topic_reason = _semantic_cache_topic_classify(query)
    if not topic:
        metrics.inc("chat_semantic_cache_block_total", {"reason": "LANE_NOT_ALLOWED"})
        metrics.inc("chat_policy_topic_miss_total", {"reason": topic_reason})
        return None
    cached = _CACHE.get_json(_semantic_cache_topic_key(topic, locale))
    entries = cached.get("entries") if isinstance(cached, dict) else None
    if not isinstance(entries, list) or not entries:
        metrics.inc("chat_semantic_cache_block_total", {"reason": "NO_CANDIDATE"})
        metrics.inc("chat_policy_topic_miss_total", {"reason": "NO_CANDIDATE"})
        return None
    threshold = _semantic_cache_similarity_threshold()
    best_response: Optional[Dict[str, Any]] = None
    best_score = 0.0
    query_norm = _normalize_query(query)
    for item in entries:
        if not isinstance(item, dict):
            continue
        response = item.get("response")
        if not isinstance(response, dict):
            continue
        candidate_query = str(item.get("query_norm") or item.get("query") or "").strip()
        if not candidate_query:
            continue
        score = _semantic_cache_similarity(query_norm, candidate_query)
        if score < threshold or score < best_score:
            continue
        best_score = score
        best_response = response
    if not isinstance(best_response, dict):
        metrics.inc("chat_semantic_cache_block_total", {"reason": "SIMILARITY_THRESHOLD"})
        metrics.inc("chat_policy_topic_miss_total", {"reason": "SIMILARITY_THRESHOLD"})
        return None
    if str(best_response.get("status") or "").strip().lower() != "ok":
        metrics.inc("chat_semantic_cache_block_total", {"reason": "BAD_STATUS"})
        metrics.inc("chat_policy_topic_miss_total", {"reason": "BAD_STATUS"})
        _semantic_cache_record_quality(ok=False, reason="BAD_STATUS")
        return None
    answer_obj = best_response.get("answer") if isinstance(best_response.get("answer"), dict) else {}
    answer_text = str(answer_obj.get("content") or "")
    citations = [str(item) for item in (best_response.get("citations") or []) if isinstance(item, str)]
    claim_safe, claim_reason = _semantic_cache_claim_safe(answer_text, citations)
    if not claim_safe:
        metrics.inc("chat_semantic_cache_block_total", {"reason": claim_reason})
        metrics.inc("chat_policy_topic_miss_total", {"reason": claim_reason})
        _semantic_cache_record_quality(ok=False, reason=claim_reason)
        return None
    _semantic_cache_record_quality(ok=True, reason="HIT")
    metrics.inc("chat_semantic_cache_hit_total", {"lane": "policy", "topic": topic})
    metrics.inc("chat_policy_topic_cache_hit_total", {"topic": topic})
    return _semantic_cache_rebind_response(best_response, trace_id, request_id)


def _semantic_cache_store(query: str, locale: str, response: Dict[str, Any]) -> None:
    if not _semantic_cache_enabled():
        return
    topic, _ = _semantic_cache_topic_classify(query)
    if not topic:
        return
    if str(response.get("status") or "").strip().lower() != "ok":
        return
    answer_obj = response.get("answer") if isinstance(response.get("answer"), dict) else {}
    answer_text = str(answer_obj.get("content") or "")
    citations = [str(item) for item in (response.get("citations") or []) if isinstance(item, str)]
    claim_safe, claim_reason = _semantic_cache_claim_safe(answer_text, citations)
    if not claim_safe:
        metrics.inc("chat_semantic_cache_block_total", {"reason": claim_reason})
        return
    key = _semantic_cache_topic_key(topic, locale)
    cached = _CACHE.get_json(key)
    entries = cached.get("entries") if isinstance(cached, dict) and isinstance(cached.get("entries"), list) else []
    query_norm = _normalize_query(query)
    next_entries: List[Dict[str, Any]] = [
        {"query": query, "query_norm": query_norm, "response": dict(response), "created_at": int(time.time())}
    ]
    for item in entries:
        if not isinstance(item, dict):
            continue
        existing_norm = _normalize_query(str(item.get("query_norm") or item.get("query") or ""))
        if existing_norm and existing_norm == query_norm:
            continue
        next_entries.append(item)
        if len(next_entries) >= _semantic_cache_max_candidates():
            break
    _CACHE.set_json(key, {"entries": next_entries, "topic": topic}, ttl=max(1, _semantic_cache_ttl_sec()))
    metrics.inc("chat_semantic_cache_store_total", {"lane": "policy", "topic": topic})


def _canonical_key(query: str, locale: str) -> str:
    try:
        return analyze_query(query, locale).get("canonical_key") or f"ck:{_hash_text(_normalize_query(query))}"
    except Exception:
        return f"ck:{_hash_text(_normalize_query(query))}"


def _locale_from_request(request: Dict[str, Any]) -> str:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    locale = client.get("locale") if isinstance(client, dict) else None
    if isinstance(locale, str) and locale.strip():
        return locale.strip()
    return os.getenv("BSL_LOCALE", "ko-KR")


def _retrieval_cache_key(canonical_key: str, locale: str, top_k: int) -> str:
    return f"rag:ret:{canonical_key}:{locale}:{top_k}"


def _answer_cache_key(canonical_key: str, locale: str) -> str:
    return f"rag:ans:{canonical_key}:{locale}:{_prompt_version()}"


def _build_context(chunks: List[dict[str, Any]]) -> Dict[str, Any]:
    return {
        "chunks": [
            {
                # Force citation keys to retrieved chunk IDs for strict post-check mapping.
                "citation_key": chunk.get("chunk_id") or chunk.get("citation_key"),
                "title": chunk.get("title") or chunk.get("source_title") or "",
                "url": chunk.get("url") or "",
                "content": chunk.get("snippet") or "",
            }
            for chunk in chunks
        ]
    }


def _format_sources(chunks: List[dict[str, Any]]) -> List[dict[str, Any]]:
    sources: List[dict[str, Any]] = []
    for chunk in chunks:
        sources.append(
            {
                "citation_key": chunk.get("citation_key") or chunk.get("chunk_id") or "",
                "doc_id": chunk.get("doc_id") or "",
                "chunk_id": chunk.get("chunk_id") or "",
                "title": chunk.get("title") or chunk.get("source_title") or "",
                "url": chunk.get("url") or "",
                "snippet": chunk.get("snippet") or "",
            }
        )
    return sources


def _fallback_defaults(reason_code: str) -> Dict[str, Any]:
    defaults: Dict[str, Dict[str, Any]] = {
        "NO_MESSAGES": {
            "message": "질문을 입력해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "CHAT_BAD_REQUEST": {
            "message": "요청 형식이 올바르지 않습니다. 질문 내용을 다시 입력해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "CHAT_INVALID_SESSION_ID": {
            "message": "세션 정보 형식이 올바르지 않습니다. 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 1000,
        },
        "CHAT_MESSAGE_TOO_LONG": {
            "message": f"질문이 너무 깁니다. {_chat_max_message_chars()}자 이내로 입력해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_HISTORY_TOO_LONG": {
            "message": f"대화 기록이 너무 깁니다. 최근 {_chat_max_history_turns()}개 발화만 남겨 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_PAYLOAD_TOO_LARGE": {
            "message": f"요청 본문이 너무 큽니다. 총 {_chat_max_total_chars()}자 이하로 줄여 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "CHAT_TOP_K_TOO_LARGE": {
            "message": f"요청 옵션 값이 너무 큽니다. top_k를 {_chat_max_top_k()} 이하로 설정해 주세요.",
            "recoverable": True,
            "next_action": "PROVIDE_REQUIRED_INFO",
            "retry_after_ms": None,
        },
        "LLM_PROMPT_BUDGET_EXCEEDED": {
            "message": "요청 컨텍스트가 너무 커서 처리 예산을 초과했습니다. 질문/대화 기록을 줄여 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "LLM_COMPLETION_BUDGET_EXCEEDED": {
            "message": "현재 응답 예산 제한으로 요청을 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "LLM_TOTAL_BUDGET_EXCEEDED": {
            "message": "요청 총 토큰 예산을 초과했습니다. 질문이나 문맥 길이를 줄여 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "LLM_CALL_RATE_LIMITED": {
            "message": "현재 요청량이 많아 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "RAG_NO_CHUNKS": {
            "message": "현재 근거 문서를 찾지 못해 확정 답변을 드리기 어렵습니다. 키워드나 조건을 조금 더 구체적으로 입력해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "RAG_LOW_SCORE": {
            "message": "관련 근거의 신뢰도가 낮아 확정 답변이 어렵습니다. 질문을 구체화하거나 다른 표현으로 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "LLM_NO_CITATIONS": {
            "message": "생성된 답변과 근거 문서가 일치하지 않아 답변을 보류했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "LLM_LOW_CITATION_COVERAGE": {
            "message": "답변이 참조한 근거 범위가 충분하지 않아 확정 답변을 보류했습니다. 질문을 조금 더 구체화해 주세요.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "PROVIDER_TIMEOUT": {
            "message": "응답 시간이 지연되어 답변을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 3000,
        },
        "OUTPUT_GUARD_EMPTY_ANSWER": {
            "message": "응답 품질 검증에 실패해 답변을 보류했습니다. 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 2000,
        },
        "OUTPUT_GUARD_INSUFFICIENT_CITATIONS": {
            "message": "근거 확인이 충분하지 않아 확정 답변을 제공할 수 없습니다.",
            "recoverable": True,
            "next_action": "REFINE_QUERY",
            "retry_after_ms": None,
        },
        "OUTPUT_GUARD_FORBIDDEN_CLAIM": {
            "message": "정책상 확정 답변이 어려운 요청입니다. 주문번호/상세 조건을 포함해 다시 질문해 주세요.",
            "recoverable": True,
            "next_action": "OPEN_SUPPORT_TICKET",
            "retry_after_ms": None,
        },
    }
    return defaults.get(
        reason_code,
        {
            "message": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 3000,
        },
    )


def _guard_blocked_message() -> str:
    return "응답 품질 검증에서 차단되었습니다."


def _fallback(
    trace_id: str,
    request_id: str,
    message: str | None,
    reason_code: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    defaults = _fallback_defaults(reason_code)
    resolved_message = (message or "").strip() or str(defaults["message"])
    fallback_count = (
        _increment_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        if session_id
        else None
    )
    escalated = False
    next_action = str(defaults["next_action"])
    if user_id and fallback_count is not None and fallback_count >= _fallback_escalation_threshold():
        next_action = "OPEN_SUPPORT_TICKET"
        escalated = True
    metrics.inc("chat_fallback_total", {"reason": reason_code})
    metrics.inc(
        "chat_error_recovery_hint_total",
        {
            "next_action": next_action,
            "reason_code": reason_code,
            "source": "rag",
        },
    )
    if escalated:
        metrics.inc("chat_fallback_escalated_total", {"reason": reason_code})
    _append_turn_event_safe(
        session_id,
        request_id,
        "TURN_FALLBACK",
        trace_id=trace_id,
        route="FALLBACK",
        reason_code=reason_code,
        payload={
            "recoverable": bool(defaults["recoverable"]),
            "next_action": next_action,
            "fallback_count": fallback_count,
            "escalated": escalated,
        },
    )
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {
            "role": "assistant",
            "content": resolved_message,
        },
        "sources": [],
        "citations": [],
        "status": "insufficient_evidence",
        "reason_code": reason_code,
        "recoverable": bool(defaults["recoverable"]),
        "next_action": next_action,
        "retry_after_ms": defaults["retry_after_ms"],
        "fallback_count": fallback_count,
        "escalated": escalated,
    }


def _is_high_risk_query(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    return any(keyword in q for keyword in _risk_band_high_keywords())


def _contains_forbidden_claim(answer: str) -> bool:
    text = (answer or "").lower()
    if not text:
        return False
    return any(keyword in text for keyword in _guard_forbidden_answer_keywords())


def _compute_risk_band(query: str, status: str, citations: List[str], guard_reason: Optional[str]) -> str:
    if status in {"error", "insufficient_evidence"}:
        return "R3"
    if guard_reason:
        return "R3"
    high_risk = _is_high_risk_query(query)
    citation_count = len(citations or [])
    if high_risk and citation_count <= 0:
        return "R3"
    if high_risk:
        return "R2"
    if citation_count <= 0:
        return "R1"
    return "R0"


def _guard_answer(
    query: str,
    answer_text: str,
    citations: List[str],
    trace_id: str,
    request_id: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not _output_guard_enabled():
        return None, None
    answer = (answer_text or "").strip()
    if not answer:
        return _fallback(trace_id, request_id, None, "OUTPUT_GUARD_EMPTY_ANSWER", session_id=session_id, user_id=user_id), "OUTPUT_GUARD_EMPTY_ANSWER"

    high_risk = _is_high_risk_query(query)
    min_citations = _guard_high_risk_min_citations() if high_risk else 1
    if len(citations or []) < min_citations:
        return _fallback(
            trace_id,
            request_id,
            None,
            "OUTPUT_GUARD_INSUFFICIENT_CITATIONS",
            session_id=session_id,
            user_id=user_id,
        ), "OUTPUT_GUARD_INSUFFICIENT_CITATIONS"

    if high_risk and _contains_forbidden_claim(answer):
        return _fallback(
            trace_id,
            request_id,
            None,
            "OUTPUT_GUARD_FORBIDDEN_CLAIM",
            session_id=session_id,
            user_id=user_id,
        ), "OUTPUT_GUARD_FORBIDDEN_CLAIM"
    return None, None


def _validate_citations(raw_citations: List[str], chunks: List[dict[str, Any]]) -> List[str]:
    allowed: set[str] = set()
    for chunk in chunks:
        citation_key = chunk.get("citation_key")
        chunk_id = chunk.get("chunk_id")
        if isinstance(citation_key, str) and citation_key:
            allowed.add(citation_key)
        if isinstance(chunk_id, str) and chunk_id:
            allowed.add(chunk_id)
    valid: List[str] = []
    for citation in raw_citations:
        if citation in allowed and citation not in valid:
            valid.append(citation)
    return valid


def _citation_doc_coverage(citations: List[str], chunks: List[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    citation_to_doc: Dict[str, str] = {}
    selected_docs: set[str] = set()
    for chunk in chunks:
        doc_id = str(chunk.get("doc_id") or "").strip()
        if not doc_id:
            continue
        selected_docs.add(doc_id)
        citation_key = str(chunk.get("citation_key") or "").strip()
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if citation_key:
            citation_to_doc[citation_key] = doc_id
        if chunk_id:
            citation_to_doc[chunk_id] = doc_id
    if not selected_docs:
        return 0.0
    cited_docs: set[str] = set()
    for citation in citations:
        doc_id = citation_to_doc.get(str(citation))
        if doc_id:
            cited_docs.add(doc_id)
    return float(len(cited_docs)) / float(len(selected_docs))


def _citation_coverage_threshold(query: str) -> float:
    if _is_high_risk_query(query):
        return _chat_high_risk_min_citation_coverage_ratio()
    return _chat_min_citation_coverage_ratio()


def _is_citation_coverage_sufficient(query: str, citations: List[str], chunks: List[dict[str, Any]]) -> tuple[bool, float, float]:
    coverage = _citation_doc_coverage(citations, chunks)
    threshold = _citation_coverage_threshold(query)
    return coverage >= threshold, coverage, threshold


def _diversity_ratio(chunks: List[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    docs = {str(chunk.get("doc_id") or "") for chunk in chunks if chunk.get("doc_id")}
    return len(docs) / float(len(chunks))


def _bad_retrieval_reason(trace: Dict[str, Any]) -> Optional[str]:
    selected = trace.get("selected") or []
    if not selected:
        return "RAG_NO_CHUNKS"
    top_score = float(selected[0].get("score") or 0.0)
    if top_score <= _bad_score_threshold():
        return "RAG_LOW_SCORE"
    if _diversity_ratio(selected) < _min_diversity_ratio():
        return "RAG_LOW_DIVERSITY"
    return None


def _sse_event(name: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"


def _extract_query_text(request: Dict[str, Any]) -> str:
    message = request.get("message") if isinstance(request.get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""


def _is_valid_session_id(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    session_id = raw.strip()
    if not session_id:
        return False
    if len(session_id) > _chat_session_id_max_len():
        return False
    return _chat_session_id_pattern().fullmatch(session_id) is not None


def _validate_chat_request(request: Dict[str, Any]) -> Optional[str]:
    if not isinstance(request, dict):
        return "CHAT_BAD_REQUEST"
    message = request.get("message")
    if not isinstance(message, dict):
        return "CHAT_BAD_REQUEST"
    content = message.get("content")
    if content is None:
        return "NO_MESSAGES"
    if not isinstance(content, str):
        return "CHAT_BAD_REQUEST"
    query = content.strip()
    if not query:
        return "NO_MESSAGES"
    if len(query) > _chat_max_message_chars():
        return "CHAT_MESSAGE_TOO_LONG"

    history = request.get("history")
    if history is not None and not isinstance(history, list):
        return "CHAT_BAD_REQUEST"
    history_items = history if isinstance(history, list) else []
    if len(history_items) > _chat_max_history_turns():
        return "CHAT_HISTORY_TOO_LONG"

    total_chars = len(query)
    for item in history_items:
        if not isinstance(item, dict):
            return "CHAT_BAD_REQUEST"
        text = item.get("content")
        if not isinstance(text, str):
            return "CHAT_BAD_REQUEST"
        if len(text) > _chat_max_message_chars():
            return "CHAT_MESSAGE_TOO_LONG"
        total_chars += len(text)

    if total_chars > _chat_max_total_chars():
        return "CHAT_PAYLOAD_TOO_LARGE"

    options = request.get("options")
    if options is not None and not isinstance(options, dict):
        return "CHAT_BAD_REQUEST"
    if isinstance(options, dict):
        top_k = options.get("top_k")
        if top_k is not None and (not isinstance(top_k, int) or top_k < 1):
            return "CHAT_BAD_REQUEST"
        if isinstance(top_k, int) and top_k > _chat_max_top_k():
            return "CHAT_TOP_K_TOO_LARGE"

    session_id = request.get("session_id")
    if session_id is not None and not _is_valid_session_id(session_id):
        return "CHAT_INVALID_SESSION_ID"
    return None


def _extract_user_id(request: Dict[str, Any]) -> Optional[str]:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    user_id = client.get("user_id") if isinstance(client, dict) else None
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return None


def _resolve_session_id(request: Dict[str, Any], user_id: Optional[str]) -> str:
    session_id = request.get("session_id")
    if _is_valid_session_id(session_id):
        return str(session_id).strip()
    if user_id:
        return f"u:{user_id}:default"
    return "anon:default"


def _fallback_escalation_threshold() -> int:
    return max(2, int(os.getenv("QS_CHAT_FALLBACK_ESCALATE_THRESHOLD", "3")))


def _fallback_counter_key(session_id: str) -> str:
    return f"chat:fallback:count:{session_id}"


def _session_user_from_session_id(session_id: Optional[str]) -> Optional[str]:
    if not isinstance(session_id, str):
        return None
    normalized = session_id.strip()
    if not normalized.startswith("u:"):
        return None
    parts = normalized.split(":")
    if len(parts) < 3:
        return None
    user_id = parts[1].strip()
    return user_id or None


def _episode_memory_consent_key(user_id: str) -> str:
    return f"chat:memory:consent:{user_id}"


def _episode_memory_data_key(user_id: str) -> str:
    return f"chat:memory:episode:{user_id}"


def _parse_optional_bool(raw: Any) -> Optional[bool]:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _extract_episode_memory_opt_in_override(request: Dict[str, Any]) -> Optional[bool]:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    if not isinstance(client, dict):
        return None
    for key in ("memory_opt_in", "episode_memory_opt_in", "memory_consent"):
        if key not in client:
            continue
        parsed = _parse_optional_bool(client.get(key))
        if parsed is not None:
            return parsed
    return None


def _redact_episode_text(text: str) -> str:
    redacted = str(text or "")
    redacted = _EPISODE_EMAIL_RE.sub("[REDACTED:EMAIL]", redacted)
    redacted = _EPISODE_PHONE_RE.sub("[REDACTED:PHONE]", redacted)
    redacted = _EPISODE_PAYMENT_RE.sub("[REDACTED:PAYMENT_ID]", redacted)
    redacted = _EPISODE_ADDRESS_RE.sub("[REDACTED:ADDRESS]", redacted)
    return redacted


def _sanitize_episode_fact(text: str) -> str:
    normalized = _query_preview(str(text or ""), max_len=_episode_memory_max_fact_len())
    if not normalized:
        return ""
    if _EPISODE_ORDER_REF_RE.search(normalized):
        return ""
    redacted = _redact_episode_text(normalized)
    if "[REDACTED:" in redacted:
        return ""
    return redacted


def _load_episode_memory_entries(user_id: Optional[str]) -> List[Dict[str, Any]]:
    if not _episode_memory_enabled():
        return []
    if not isinstance(user_id, str) or not user_id.strip():
        return []
    cached = _CACHE.get_json(_episode_memory_data_key(user_id.strip()))
    entries = cached.get("entries") if isinstance(cached, dict) and isinstance(cached.get("entries"), list) else []
    result: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact") or "").strip()
        if not fact:
            continue
        result.append(
            {
                "fact": fact,
                "updated_at": int(item.get("updated_at") or 0),
                "session_id": str(item.get("session_id") or ""),
            }
        )
        if len(result) >= _episode_memory_max_items():
            break
    return result


def _current_episode_memory_opt_in(user_id: Optional[str]) -> bool:
    if not _episode_memory_enabled():
        return False
    if not isinstance(user_id, str) or not user_id.strip():
        return False
    cached = _CACHE.get_json(_episode_memory_consent_key(user_id.strip()))
    if isinstance(cached, dict) and isinstance(cached.get("opt_in"), bool):
        return bool(cached.get("opt_in"))
    return _episode_memory_default_opt_in()


def _resolve_episode_memory_opt_in(
    request: Dict[str, Any],
    *,
    user_id: Optional[str],
    session_id: str,
    trace_id: str,
    request_id: str,
) -> bool:
    if not _episode_memory_enabled():
        metrics.inc("chat_memory_opt_in_total", {"result": "disabled", "source": "config"})
        return False
    if not isinstance(user_id, str) or not user_id.strip():
        metrics.inc("chat_memory_opt_in_total", {"result": "missing_user", "source": "request"})
        return False
    normalized_user = user_id.strip()
    override = _extract_episode_memory_opt_in_override(request)
    if override is None:
        opted_in = _current_episode_memory_opt_in(normalized_user)
        metrics.inc(
            "chat_memory_opt_in_total",
            {"result": "opt_in" if opted_in else "opt_out", "source": "cached_or_default"},
        )
        return opted_in

    ttl_sec = _episode_memory_ttl_sec()
    _CACHE.set_json(
        _episode_memory_consent_key(normalized_user),
        {"opt_in": bool(override), "updated_at": int(time.time()), "request_id": request_id},
        ttl=ttl_sec,
    )
    if not override:
        _CACHE.set_json(_episode_memory_data_key(normalized_user), {"entries": [], "cleared": True}, ttl=1)
    _append_action_audit_safe(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type="EPISODE_MEMORY_CONSENT",
        reason_code="MEMORY_OPT_IN" if override else "MEMORY_OPT_OUT",
        metadata={"user_id": normalized_user, "opt_in": bool(override)},
    )
    metrics.inc(
        "chat_memory_opt_in_total",
        {"result": "opt_in" if override else "opt_out", "source": "request"},
    )
    return bool(override)


def _episode_memory_facts(user_id: Optional[str], *, opted_in: bool) -> List[str]:
    if not _episode_memory_enabled():
        metrics.inc("chat_memory_retrieval_total", {"result": "disabled"})
        return []
    if not isinstance(user_id, str) or not user_id.strip():
        metrics.inc("chat_memory_retrieval_total", {"result": "no_user"})
        return []
    if not opted_in:
        metrics.inc("chat_memory_retrieval_total", {"result": "no_consent"})
        return []
    entries = _load_episode_memory_entries(user_id)
    if not entries:
        metrics.inc("chat_memory_retrieval_total", {"result": "miss"})
        return []
    facts = [str(item.get("fact") or "").strip() for item in entries if str(item.get("fact") or "").strip()]
    if not facts:
        metrics.inc("chat_memory_retrieval_total", {"result": "miss"})
        return []
    metrics.inc("chat_memory_retrieval_total", {"result": "hit"})
    return facts[: _episode_memory_prompt_items()]


def _remember_episode_memory_fact(
    *,
    user_id: Optional[str],
    session_id: str,
    query_text: str,
    trace_id: str,
    request_id: str,
    opted_in: bool,
) -> None:
    if not _episode_memory_enabled():
        return
    if not isinstance(user_id, str) or not user_id.strip():
        return
    if not opted_in:
        return
    fact = _sanitize_episode_fact(query_text)
    if not fact:
        metrics.inc("chat_memory_store_total", {"result": "filtered"})
        return
    normalized_user = user_id.strip()
    now_ts = int(time.time())
    entries = _load_episode_memory_entries(normalized_user)
    next_entries: List[Dict[str, Any]] = [{"fact": fact, "updated_at": now_ts, "session_id": session_id}]
    for item in entries:
        item_fact = str(item.get("fact") or "").strip()
        if not item_fact or item_fact == fact:
            continue
        next_entries.append(
            {
                "fact": item_fact,
                "updated_at": int(item.get("updated_at") or 0),
                "session_id": str(item.get("session_id") or ""),
            }
        )
        if len(next_entries) >= _episode_memory_max_items():
            break
    _CACHE.set_json(
        _episode_memory_data_key(normalized_user),
        {"entries": next_entries},
        ttl=_episode_memory_ttl_sec(),
    )
    summary = " | ".join([str(item.get("fact") or "") for item in next_entries[: _episode_memory_max_items()] if str(item.get("fact") or "")])
    _write_durable_session_state(
        session_id,
        user_id=normalized_user,
        trace_id=trace_id,
        request_id=request_id,
        summary_short=summary,
        summary_short_set=True,
    )
    metrics.inc("chat_memory_store_total", {"result": "ok"})


def _delete_episode_memory(user_id: Optional[str]) -> int:
    if not _episode_memory_enabled():
        metrics.inc("chat_memory_delete_total", {"result": "disabled"})
        return 0
    if not isinstance(user_id, str) or not user_id.strip():
        metrics.inc("chat_memory_delete_total", {"result": "no_user"})
        return 0
    normalized_user = user_id.strip()
    entries = _load_episode_memory_entries(normalized_user)
    _CACHE.set_json(_episode_memory_data_key(normalized_user), {"entries": [], "cleared": True}, ttl=1)
    metrics.inc("chat_memory_delete_total", {"result": "ok"})
    return len(entries)


def _episode_memory_snapshot(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not _episode_memory_enabled():
        return {"enabled": False, "opt_in": False, "count": 0, "items": []}
    if not isinstance(user_id, str) or not user_id.strip():
        return None
    opted_in = _current_episode_memory_opt_in(user_id)
    entries = _load_episode_memory_entries(user_id) if opted_in else []
    return {
        "enabled": True,
        "opt_in": bool(opted_in),
        "count": len(entries),
        "items": [str(item.get("fact") or "") for item in entries[: _episode_memory_prompt_items()] if str(item.get("fact") or "")],
    }


def _query_fingerprint(query: str) -> str:
    normalized = (query or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _write_durable_session_state(
    session_id: Optional[str],
    *,
    user_id: Optional[str],
    trace_id: Optional[str],
    request_id: Optional[str],
    fallback_count: Optional[int] = None,
    unresolved_context: Any = None,
    unresolved_context_set: bool = False,
    summary_short: Any = None,
    summary_short_set: bool = False,
) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    durable_user_id = user_id or _session_user_from_session_id(session_id)
    kwargs: Dict[str, Any] = {}
    if unresolved_context_set:
        kwargs["unresolved_context"] = unresolved_context
    if summary_short_set:
        kwargs["summary_short"] = summary_short
    return upsert_session_state(
        session_id,
        user_id=durable_user_id,
        trace_id=trace_id,
        request_id=request_id,
        fallback_count=fallback_count,
        last_turn_id=request_id,
        idempotency_key=request_id,
        **kwargs,
    )


def _append_turn_event_safe(
    session_id: Optional[str],
    request_id: str,
    event_type: str,
    *,
    trace_id: str,
    route: Optional[str],
    reason_code: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_id or not request_id:
        return
    append_turn_event(
        conversation_id=session_id,
        turn_id=request_id,
        event_type=event_type,
        trace_id=trace_id,
        request_id=request_id,
        route=route,
        reason_code=reason_code,
        payload=payload,
    )


def _append_action_audit_safe(
    session_id: Optional[str],
    *,
    trace_id: str,
    request_id: str,
    action_type: str,
    reason_code: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_id:
        return
    actor_user = _session_user_from_session_id(session_id)
    append_action_audit(
        conversation_id=session_id,
        action_type=action_type,
        action_state="EXECUTED",
        decision="ALLOW",
        result="SUCCESS",
        actor_user_id=actor_user,
        actor_admin_id=None,
        target_ref=session_id,
        auth_context={"session_id": session_id},
        trace_id=trace_id,
        request_id=request_id,
        reason_code=reason_code,
        idempotency_key=f"{action_type}:{session_id}:{request_id}",
        metadata=metadata or {},
    )


def _increment_fallback_count(
    session_id: str,
    *,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> int:
    key = _fallback_counter_key(session_id)
    cached = _CACHE.get_json(key)
    count = 0
    if isinstance(cached, dict):
        raw_count = cached.get("count")
        if isinstance(raw_count, int) and raw_count >= 0:
            count = raw_count
    count += 1
    _CACHE.set_json(key, {"count": count}, ttl=max(60, _answer_cache_ttl_sec() * 2))
    stored = _write_durable_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        fallback_count=count,
    )
    if isinstance(stored, dict):
        persisted_count = stored.get("fallback_count")
        if isinstance(persisted_count, int) and persisted_count >= 0:
            count = persisted_count
    return count


def _reset_fallback_count(
    session_id: Optional[str],
    *,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    if not session_id:
        return
    _CACHE.set_json(_fallback_counter_key(session_id), {"count": 0}, ttl=5)
    _write_durable_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        fallback_count=0,
    )


def _load_fallback_count(session_id: str) -> int:
    durable = get_durable_chat_session_state(session_id)
    if isinstance(durable, dict):
        durable_count = durable.get("fallback_count")
        if isinstance(durable_count, int) and durable_count >= 0:
            return durable_count
    cached = _CACHE.get_json(_fallback_counter_key(session_id))
    if isinstance(cached, dict):
        raw_count = cached.get("count")
        if isinstance(raw_count, int) and raw_count >= 0:
            return raw_count
    return 0


def _unresolved_context_key(session_id: str) -> str:
    return f"chat:unresolved:{session_id}"


def _save_unresolved_context(
    session_id: Optional[str],
    query: str,
    reason_code: str,
    *,
    trace_id: str,
    request_id: str,
    user_id: Optional[str] = None,
) -> None:
    if not session_id:
        return
    trimmed_query = (query or "").strip()
    context = {
        "query": trimmed_query,
        "reason_code": reason_code,
        "trace_id": trace_id,
        "request_id": request_id,
        "updated_at": int(time.time()),
        "query_hash": _query_fingerprint(trimmed_query),
    }
    _CACHE.set_json(
        _unresolved_context_key(session_id),
        context,
        ttl=_unresolved_context_ttl_sec(),
    )
    _write_durable_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        unresolved_context=context,
        unresolved_context_set=True,
    )


def _clear_unresolved_context(
    session_id: Optional[str],
    *,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    if not session_id:
        return
    _CACHE.set_json(_unresolved_context_key(session_id), {"cleared": True}, ttl=1)
    _write_durable_session_state(
        session_id,
        user_id=user_id,
        trace_id=trace_id,
        request_id=request_id,
        unresolved_context=None,
        unresolved_context_set=True,
    )


def _load_unresolved_context(session_id: str) -> Optional[Dict[str, Any]]:
    durable = get_durable_chat_session_state(session_id)
    if isinstance(durable, dict):
        unresolved = durable.get("unresolved_context")
        if isinstance(unresolved, dict):
            return unresolved
        if unresolved is None:
            return None
    cached = _CACHE.get_json(_unresolved_context_key(session_id))
    if not isinstance(cached, dict):
        return None
    if cached.get("cleared") is True:
        return None
    return cached


def _query_preview(text: str, *, max_len: int = 120) -> str:
    normalized = " ".join((text or "").split()).strip()
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max_len - 1]}..."


def _resolve_top_k(request: Dict[str, Any]) -> int:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    top_k = options.get("top_k")
    if isinstance(top_k, int) and top_k > 0:
        return min(top_k, _chat_max_top_k())
    return min(int(os.getenv("QS_RAG_TOP_K", "6")), _chat_max_top_k())


def _resolve_top_n(request: Dict[str, Any]) -> Optional[int]:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    top_n = options.get("top_n")
    if isinstance(top_n, int) and top_n > 0:
        return top_n
    return None


def _resolve_rerank_override(request: Dict[str, Any]) -> Optional[bool]:
    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    rerank = options.get("rag_rerank")
    if isinstance(rerank, bool):
        return rerank
    return None


async def _retrieve_with_optional_rewrite(
    request: Dict[str, Any],
    query: str,
    canonical_key: str,
    locale: str,
    trace_id: str,
    request_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    top_k = _resolve_top_k(request)
    top_n = _resolve_top_n(request)
    rerank_override = _resolve_rerank_override(request)
    retrieval_cache_key = _retrieval_cache_key(canonical_key, locale, top_k)

    cached_trace = _CACHE.get_json(retrieval_cache_key)
    if isinstance(cached_trace, dict) and cached_trace.get("trace"):
        metrics.inc("chat_requests_total", {"decision": "retrieval_cache_hit"})
        trace = cached_trace.get("trace")
        return trace, {
            "retrieval_cache_hit": True,
            "rewrite_applied": False,
            "rewrite_reason": None,
            "rewrite_strategy": "none",
            "rewritten_query": query,
            "initial_query": query,
            "bad_reason": _bad_retrieval_reason(trace),
        }

    trace = await retrieve_chunks_with_trace(
        query,
        trace_id,
        request_id,
        top_k=top_k,
        top_n=top_n,
        rerank_enabled=rerank_override,
    )
    bad_reason = _bad_retrieval_reason(trace)
    rewrite_meta = {
        "retrieval_cache_hit": False,
        "rewrite_applied": False,
        "rewrite_reason": bad_reason,
        "rewrite_strategy": "none",
        "rewritten_query": query,
        "initial_query": query,
        "bad_reason": bad_reason,
    }

    if bad_reason and _rewrite_on_bad_enabled():
        candidates = await retrieve_candidates(query, trace_id, request_id, top_k=5)
        rewrite_payload, rewrite_detail = await run_rewrite(
            query,
            trace_id,
            request_id,
            reason=bad_reason,
            locale=locale,
            candidates=candidates,
        )
        rewritten = rewrite_payload.get("rewritten") if isinstance(rewrite_payload, dict) else None
        if rewrite_payload.get("applied") and isinstance(rewritten, str) and rewritten.strip() and rewritten.strip() != query.strip():
            rewrite_meta["rewrite_applied"] = True
            rewrite_meta["rewrite_strategy"] = rewrite_payload.get("method") or "rewrite"
            rewrite_meta["rewritten_query"] = rewritten.strip()
            trace2 = await retrieve_chunks_with_trace(
                rewritten.strip(),
                trace_id,
                request_id,
                top_k=top_k,
                top_n=top_n,
                rerank_enabled=rerank_override,
            )
            selected_before = trace.get("selected") or []
            selected_after = trace2.get("selected") or []
            if len(selected_after) > len(selected_before) or (selected_before and selected_after and float(selected_after[0].get("score") or 0.0) > float(selected_before[0].get("score") or 0.0)):
                trace = trace2
                rewrite_meta["rewrite_reason"] = bad_reason
            else:
                rewrite_meta["rewrite_reason"] = "rewrite_not_improved"
        else:
            reject_reason = rewrite_detail.get("reject_reason") if isinstance(rewrite_detail, dict) else None
            rewrite_meta["rewrite_reason"] = str(reject_reason or bad_reason)

    _CACHE.set_json(retrieval_cache_key, {"trace": trace}, ttl=max(1, _retrieval_cache_ttl_sec()))
    return trace, rewrite_meta


def _build_llm_payload(
    request: Dict[str, Any],
    trace_id: str,
    request_id: str,
    query: str,
    chunks: List[dict[str, Any]],
    *,
    memory_facts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    messages: List[dict[str, Any]] = [{"role": "system", "content": "Answer using provided sources and cite them."}]
    if isinstance(memory_facts, list):
        facts = [str(item).strip() for item in memory_facts if isinstance(item, str) and str(item).strip()]
        if facts:
            memory_lines = "\n".join([f"- {item}" for item in facts[: _episode_memory_prompt_items()]])
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use these user-approved long-term memory facts only when relevant.\n"
                        "Do not infer sensitive details.\n"
                        f"{memory_lines}"
                    ),
                }
            )
    history = request.get("history") or []
    if isinstance(history, list):
        for item in history[-6:]:
            if isinstance(item, dict) and item.get("role") and item.get("content"):
                messages.append({"role": item.get("role"), "content": item.get("content")})
    messages.append({"role": "user", "content": query})
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "model": _llm_model(),
        "max_tokens": _llm_max_completion_tokens_per_turn(),
        "messages": messages,
        "context": _build_context(chunks),
        "citations_required": True,
    }


async def _call_llm_json(payload: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    started = time.perf_counter()
    all_providers = _llm_provider_chain()
    providers = _apply_provider_blocklist(all_providers, mode="json")
    forced = _llm_forced_provider()
    forced_blocked = _is_forced_provider_blocked(all_providers, providers)
    if forced_blocked and forced:
        metrics.inc("chat_provider_forced_route_total", {"provider": forced, "reason": "blocked", "mode": "json"})
    providers = _apply_intent_routing(providers, payload, mode="json")
    providers = _apply_cost_steering(providers, payload, mode="json")
    providers = _apply_provider_health(providers, mode="json")
    if not forced_blocked:
        providers = _apply_provider_override(providers, mode="json")
    max_attempts = _llm_max_provider_attempts_per_turn()
    if len(providers) > max_attempts:
        metrics.inc(
            "chat_llm_provider_attempt_limited_total",
            {"mode": "json", "max_attempts": str(max_attempts)},
        )
        providers = providers[:max_attempts]
    last_error: Exception | None = None
    async with httpx.AsyncClient() as client:
        for idx, (provider, base_url) in enumerate(providers):
            try:
                response = await client.post(f"{base_url}/v1/generate", json=payload, headers=headers, timeout=_llm_timeout_sec())
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                metrics.inc("chat_provider_route_total", {"provider": provider, "result": "timeout", "mode": "json"})
                _record_provider_telemetry(provider, base_url, success=False)
                _mark_provider_unhealthy(provider, "timeout")
                if idx + 1 < len(providers):
                    metrics.inc(
                        "chat_provider_failover_total",
                        {"from": provider, "to": providers[idx + 1][0], "reason": "timeout", "mode": "json"},
                    )
                    continue
                raise
            except Exception as exc:
                last_error = exc
                metrics.inc("chat_provider_route_total", {"provider": provider, "result": "error", "mode": "json"})
                _record_provider_telemetry(provider, base_url, success=False)
                raise
            status_code = int(response.status_code)
            if status_code >= 400:
                reason = f"http_{status_code}"
                metrics.inc("chat_provider_route_total", {"provider": provider, "result": reason, "mode": "json"})
                _record_provider_telemetry(provider, base_url, success=False)
                if _is_failover_status(status_code) and idx + 1 < len(providers):
                    _mark_provider_unhealthy(provider, reason)
                    metrics.inc(
                        "chat_provider_failover_total",
                        {"from": provider, "to": providers[idx + 1][0], "reason": reason, "mode": "json"},
                    )
                    continue
                response.raise_for_status()
            try:
                data = response.json()
            except Exception as exc:
                last_error = exc
                metrics.inc("chat_provider_route_total", {"provider": provider, "result": "invalid_json", "mode": "json"})
                _record_provider_telemetry(provider, base_url, success=False)
                raise
            metrics.inc("chat_provider_route_total", {"provider": provider, "result": "ok", "mode": "json"})
            _record_provider_telemetry(provider, base_url, success=True)
            _clear_provider_unhealthy(provider)
            took_ms = int((time.perf_counter() - started) * 1000)
            metrics.inc("llm_generate_latency_ms", value=max(0, took_ms))
            return data
    raise last_error or RuntimeError("llm_provider_unavailable")


async def _stream_llm(
    payload: Dict[str, Any],
    trace_id: str,
    request_id: str,
) -> tuple[AsyncIterator[str], dict[str, Any]]:
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    first_token_reported = False
    started = time.perf_counter()
    stream_state: dict[str, Any] = {
        "answer": "",
        "citations": [],
        "llm_error": None,
        "done_status": "ok",
    }

    async def generator() -> AsyncIterator[str]:
        nonlocal first_token_reported
        all_providers = _llm_provider_chain()
        providers = _apply_provider_blocklist(all_providers, mode="stream")
        forced = _llm_forced_provider()
        forced_blocked = _is_forced_provider_blocked(all_providers, providers)
        if forced_blocked and forced:
            metrics.inc("chat_provider_forced_route_total", {"provider": forced, "reason": "blocked", "mode": "stream"})
        providers = _apply_intent_routing(providers, payload, mode="stream")
        providers = _apply_cost_steering(providers, payload, mode="stream")
        providers = _apply_provider_health(providers, mode="stream")
        if not forced_blocked:
            providers = _apply_provider_override(providers, mode="stream")
        max_attempts = _llm_max_provider_attempts_per_turn()
        if len(providers) > max_attempts:
            metrics.inc(
                "chat_llm_provider_attempt_limited_total",
                {"mode": "stream", "max_attempts": str(max_attempts)},
            )
            providers = providers[:max_attempts]
        last_error: Optional[Exception] = None
        async with httpx.AsyncClient() as client:
            for idx, (provider, base_url) in enumerate(providers):
                event_name = "message"
                data_lines: List[str] = []
                try:
                    async with client.stream(
                        "POST",
                        f"{base_url}/v1/generate?stream=true",
                        json={**payload, "stream": True},
                        headers=headers,
                        timeout=_llm_timeout_sec(),
                    ) as response:
                        status_code = int(response.status_code)
                        if status_code >= 400:
                            reason = f"http_{status_code}"
                            metrics.inc(
                                "chat_provider_route_total",
                                {"provider": provider, "result": reason, "mode": "stream"},
                            )
                            _record_provider_telemetry(provider, base_url, success=False)
                            if _is_failover_status(status_code) and idx + 1 < len(providers):
                                _mark_provider_unhealthy(provider, reason)
                                metrics.inc(
                                    "chat_provider_failover_total",
                                    {"from": provider, "to": providers[idx + 1][0], "reason": reason, "mode": "stream"},
                                )
                                continue
                            response.raise_for_status()
                        async for raw_line in response.aiter_lines():
                            line = raw_line if raw_line is not None else ""
                            if line.startswith("event:"):
                                event_name = line.split(":", 1)[1].strip() or "message"
                            elif line.startswith("data:"):
                                data_lines.append(line.split(":", 1)[1].strip())
                            elif line == "":
                                if not data_lines:
                                    event_name = "message"
                                    continue
                                data = "\n".join(data_lines)
                                if event_name == "delta":
                                    if not first_token_reported:
                                        first_token_reported = True
                                        first_token_ms = int((time.perf_counter() - started) * 1000)
                                        metrics.inc("chat_first_token_latency_ms", value=max(0, first_token_ms))
                                    try:
                                        parsed = json.loads(data)
                                        delta = parsed.get("delta") if isinstance(parsed, dict) else None
                                        if isinstance(delta, str):
                                            stream_state["answer"] += delta
                                    except Exception:
                                        stream_state["answer"] += data
                                elif event_name == "done":
                                    try:
                                        parsed = json.loads(data)
                                        if isinstance(parsed, dict):
                                            done_status = parsed.get("status")
                                            if isinstance(done_status, str) and done_status:
                                                stream_state["done_status"] = done_status
                                            if isinstance(parsed.get("citations"), list):
                                                stream_state["citations"] = [str(item) for item in parsed.get("citations") if isinstance(item, str)]
                                    except Exception:
                                        pass
                                    data_lines = []
                                    event_name = "message"
                                    continue
                                yield _sse_event(event_name, data)
                                data_lines = []
                                event_name = "message"
                    metrics.inc("chat_provider_route_total", {"provider": provider, "result": "ok", "mode": "stream"})
                    _record_provider_telemetry(provider, base_url, success=True)
                    _clear_provider_unhealthy(provider)
                    took_ms = int((time.perf_counter() - started) * 1000)
                    metrics.inc("llm_generate_latency_ms", value=max(0, took_ms))
                    return
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    metrics.inc("chat_provider_route_total", {"provider": provider, "result": "timeout", "mode": "stream"})
                    _record_provider_telemetry(provider, base_url, success=False)
                    _mark_provider_unhealthy(provider, "timeout")
                    if idx + 1 < len(providers) and not stream_state.get("answer"):
                        metrics.inc(
                            "chat_provider_failover_total",
                            {"from": provider, "to": providers[idx + 1][0], "reason": "timeout", "mode": "stream"},
                        )
                        continue
                    stream_state["llm_error"] = str(exc)
                    break
                except Exception as exc:
                    last_error = exc
                    stream_state["llm_error"] = str(exc)
                    metrics.inc("chat_provider_route_total", {"provider": provider, "result": "error", "mode": "stream"})
                    _record_provider_telemetry(provider, base_url, success=False)
                    break

        if stream_state.get("llm_error") is None and last_error is not None:
            stream_state["llm_error"] = str(last_error)
        if stream_state.get("llm_error"):
            metrics.inc("chat_fallback_total", {"reason": "PROVIDER_TIMEOUT"})
            _record_chat_timeout("llm_stream")
            yield _sse_event("error", {"code": "PROVIDER_TIMEOUT", "message": "LLM 응답 지연으로 처리하지 못했습니다."})
            yield _sse_event("done", {"status": "error", "citations": []})

    return generator(), stream_state


async def _prepare_chat(
    request: Dict[str, Any],
    trace_id: str,
    request_id: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    query = _extract_query_text(request)
    if not query.strip():
        return {
            "ok": False,
            "reason": "NO_MESSAGES",
            "response": _fallback(trace_id, request_id, None, "NO_MESSAGES", session_id=session_id, user_id=user_id),
        }

    locale = _locale_from_request(request)
    canonical_key = _canonical_key(query, locale)
    trace, rewrite_meta = await _retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id)
    selected = trace.get("selected") or []
    if not selected:
        return {
            "ok": False,
            "reason": "RAG_NO_CHUNKS",
            "response": _fallback(trace_id, request_id, None, "RAG_NO_CHUNKS", session_id=session_id, user_id=user_id),
            "canonical_key": canonical_key,
            "locale": locale,
            "trace": trace,
            "rewrite": rewrite_meta,
        }

    return {
        "ok": True,
        "query": rewrite_meta.get("rewritten_query") or query,
        "canonical_key": canonical_key,
        "locale": locale,
        "trace": trace,
        "rewrite": rewrite_meta,
        "selected": selected,
    }


async def _run_chat_impl(
    request: Dict[str, Any],
    trace_id: str,
    request_id: str,
    *,
    allow_tools: bool,
) -> Dict[str, Any]:
    user_id = _extract_user_id(request)
    session_id = _resolve_session_id(request, user_id)
    query_text = _extract_query_text(request)
    memory_opt_in = _resolve_episode_memory_opt_in(
        request,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        request_id=request_id,
    )
    memory_facts = _episode_memory_facts(user_id, opted_in=memory_opt_in)
    _append_turn_event_safe(
        session_id,
        request_id,
        "TURN_RECEIVED",
        trace_id=trace_id,
        route="INPUT",
        reason_code=None,
        payload={
            "query_len": len((query_text or "").strip()),
            "query_hash": _query_fingerprint(query_text),
            "stream": False,
        },
    )
    validation_reason = _validate_chat_request(request)
    if validation_reason:
        metrics.inc("chat_validation_fail_total", {"reason": validation_reason})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, validation_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query_text,
            validation_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        return response
    tool_response = await run_tool_chat(request, trace_id, request_id) if allow_tools else None
    if tool_response is not None:
        _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        if str(tool_response.get("status") or "").strip().lower() == "ok":
            _remember_episode_memory_fact(
                user_id=user_id,
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                request_id=request_id,
                opted_in=memory_opt_in,
            )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_COMPLETED",
            trace_id=trace_id,
            route="TOOL_PATH",
            reason_code=str(tool_response.get("reason_code") or "OK"),
            payload={"status": str(tool_response.get("status") or "ok")},
        )
        metrics.inc("chat_requests_total", {"decision": "tool_path"})
        return tool_response

    prepared = await _prepare_chat(request, trace_id, request_id, session_id=session_id, user_id=user_id)
    if not prepared.get("ok"):
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = prepared.get("response")
        if isinstance(response, dict):
            _save_unresolved_context(
                session_id,
                query_text,
                str(response.get("reason_code") or str(prepared.get("reason") or "RAG_NO_CHUNKS")),
                trace_id=trace_id,
                request_id=request_id,
                user_id=user_id,
            )
        return response

    query = prepared.get("query") or ""
    canonical_key = prepared.get("canonical_key")
    locale = prepared.get("locale")
    selected = prepared.get("selected") or []
    answer_cache_key = _answer_cache_key(canonical_key, locale)

    if _answer_cache_enabled():
        cached = _CACHE.get_json(answer_cache_key)
        if isinstance(cached, dict) and cached.get("response"):
            _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
            _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
            _remember_episode_memory_fact(
                user_id=user_id,
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                request_id=request_id,
                opted_in=memory_opt_in,
            )
            _append_turn_event_safe(
                session_id,
                request_id,
                "TURN_COMPLETED",
                trace_id=trace_id,
                route="ANSWER_CACHE_HIT",
                reason_code="OK",
                payload={"status": "ok", "cache": "answer"},
            )
            metrics.inc("chat_requests_total", {"decision": "answer_cache_hit"})
            return cached.get("response")

    semantic_cached = _semantic_cache_lookup(query, str(locale), trace_id, request_id)
    if isinstance(semantic_cached, dict):
        semantic_citations = [str(item) for item in (semantic_cached.get("citations") or []) if isinstance(item, str)]
        _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        _remember_episode_memory_fact(
            user_id=user_id,
            session_id=session_id,
            query_text=query_text,
            trace_id=trace_id,
            request_id=request_id,
            opted_in=memory_opt_in,
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_COMPLETED",
            trace_id=trace_id,
            route="SEMANTIC_CACHE_HIT",
            reason_code=str(semantic_cached.get("reason_code") or "OK"),
            payload={"status": str(semantic_cached.get("status") or "ok"), "cache": "semantic"},
        )
        metrics.inc("chat_answer_risk_band_total", {"band": _compute_risk_band(query, str(semantic_cached.get("status") or "ok"), semantic_citations, None)})
        metrics.inc("chat_requests_total", {"decision": "semantic_cache_hit"})
        return semantic_cached

    payload = _build_llm_payload(
        request,
        trace_id,
        request_id,
        query,
        selected,
        memory_facts=memory_facts,
    )
    admission_reason = _admission_block_reason(payload, mode="json")
    if admission_reason:
        metrics.inc("chat_admission_block_total", {"reason": admission_reason, "mode": "json"})
        response = _fallback(trace_id, request_id, None, admission_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            admission_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_BLOCKED",
            trace_id=trace_id,
            route="ADMISSION",
            reason_code=admission_reason,
            payload={"stream": False},
        )
        _append_action_audit_safe(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type="LLM_ADMISSION_BLOCK",
            reason_code=admission_reason,
            metadata={"mode": "json"},
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return response
    call_budget_reason = _reserve_llm_call_budget(session_id, user_id, mode="json")
    if call_budget_reason:
        metrics.inc("chat_admission_block_total", {"reason": call_budget_reason, "mode": "json"})
        response = _fallback(trace_id, request_id, None, call_budget_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            call_budget_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_BLOCKED",
            trace_id=trace_id,
            route="ADMISSION",
            reason_code=call_budget_reason,
            payload={"stream": False},
        )
        _append_action_audit_safe(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type="LLM_ADMISSION_BLOCK",
            reason_code=call_budget_reason,
            metadata={"mode": "json"},
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return response
    try:
        data = await _call_llm_json(payload, trace_id, request_id)
    except Exception:
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        _record_chat_timeout("llm_generate")
        response = _fallback(trace_id, request_id, None, "PROVIDER_TIMEOUT", session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            "PROVIDER_TIMEOUT",
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        return response

    answer_text = str(data.get("content") or "")
    raw_citations = data.get("citations") if isinstance(data.get("citations"), list) else _extract_citations_from_text(answer_text)
    citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
    if not citations:
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, "LLM_NO_CITATIONS", session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            "LLM_NO_CITATIONS",
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        return response
    coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
    if not coverage_ok:
        metrics.inc(
            "chat_citation_coverage_block_total",
            {
                "risk": "high" if _is_high_risk_query(query) else "normal",
                "threshold": f"{coverage_threshold:.2f}",
            },
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        response = _fallback(trace_id, request_id, None, "LLM_LOW_CITATION_COVERAGE", session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            "LLM_LOW_CITATION_COVERAGE",
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        return response

    guarded_response, guard_reason = _guard_answer(
        query,
        answer_text,
        citations,
        trace_id,
        request_id,
        session_id=session_id,
        user_id=user_id,
    )
    if guarded_response is not None:
        metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
        metrics.inc(
            "chat_answer_risk_band_total",
            {"band": _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)},
        )
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        _save_unresolved_context(
            session_id,
            query,
            str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        return guarded_response

    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {"role": "assistant", "content": answer_text},
        "sources": _format_sources(selected),
        "citations": citations,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
        "fallback_count": 0,
        "escalated": False,
    }
    metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
    metrics.inc("chat_answer_risk_band_total", {"band": _compute_risk_band(query, "ok", citations, None)})
    if _answer_cache_enabled():
        _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))
    _semantic_cache_store(query, str(locale), response)

    _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
    _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
    _remember_episode_memory_fact(
        user_id=user_id,
        session_id=session_id,
        query_text=query_text,
        trace_id=trace_id,
        request_id=request_id,
        opted_in=memory_opt_in,
    )
    _append_turn_event_safe(
        session_id,
        request_id,
        "TURN_COMPLETED",
        trace_id=trace_id,
        route="ANSWER",
        reason_code="OK",
        payload={"status": "ok", "citation_count": len(citations)},
    )
    metrics.inc("chat_requests_total", {"decision": "ok"})
    return response


async def _run_chat_stream_impl(
    request: Dict[str, Any],
    trace_id: str,
    request_id: str,
    *,
    allow_tools: bool,
) -> AsyncIterator[str]:
    user_id = _extract_user_id(request)
    session_id = _resolve_session_id(request, user_id)
    query_text = _extract_query_text(request)
    memory_opt_in = _resolve_episode_memory_opt_in(
        request,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        request_id=request_id,
    )
    memory_facts = _episode_memory_facts(user_id, opted_in=memory_opt_in)
    _append_turn_event_safe(
        session_id,
        request_id,
        "TURN_RECEIVED",
        trace_id=trace_id,
        route="INPUT",
        reason_code=None,
        payload={
            "query_len": len((query_text or "").strip()),
            "query_hash": _query_fingerprint(query_text),
            "stream": True,
        },
    )
    validation_reason = _validate_chat_request(request)
    if validation_reason:
        metrics.inc("chat_validation_fail_total", {"reason": validation_reason})
        response = _fallback(trace_id, request_id, None, validation_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query_text,
            validation_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        risk_band = _compute_risk_band("", response.get("status", "insufficient_evidence"), [], validation_reason)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": response.get("status"),
                "risk_band": risk_band,
                "reason_code": response.get("reason_code"),
                "recoverable": response.get("recoverable"),
                "next_action": response.get("next_action"),
                "retry_after_ms": response.get("retry_after_ms"),
                "fallback_count": response.get("fallback_count"),
                "escalated": response.get("escalated"),
            },
        )
        yield _sse_event("delta", {"delta": str(response.get("answer", {}).get("content") if isinstance(response.get("answer"), dict) else "")})
        yield _sse_event(
            "done",
            {
                "status": response.get("status"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": response.get("reason_code"),
                "recoverable": response.get("recoverable"),
                "next_action": response.get("next_action"),
                "retry_after_ms": response.get("retry_after_ms"),
                "fallback_count": response.get("fallback_count"),
                "escalated": response.get("escalated"),
            },
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    tool_response = await run_tool_chat(request, trace_id, request_id) if allow_tools else None
    if tool_response is not None:
        _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id, user_id=user_id)
        if str(tool_response.get("status") or "").strip().lower() == "ok":
            _remember_episode_memory_fact(
                user_id=user_id,
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                request_id=request_id,
                opted_in=memory_opt_in,
            )
        answer = tool_response.get("answer", {}) if isinstance(tool_response.get("answer"), dict) else {}
        citations = [str(item) for item in (tool_response.get("citations") or []) if isinstance(item, str)]
        sources = tool_response.get("sources") if isinstance(tool_response.get("sources"), list) else []
        status = str(tool_response.get("status") or "ok")
        reason_code = str(tool_response.get("reason_code") or "OK")
        recoverable = bool(tool_response.get("recoverable")) if isinstance(tool_response.get("recoverable"), bool) else False
        next_action = str(tool_response.get("next_action") or "NONE")
        retry_after_ms = tool_response.get("retry_after_ms")
        fallback_count = tool_response.get("fallback_count")
        escalated = bool(tool_response.get("escalated")) if isinstance(tool_response.get("escalated"), bool) else False
        risk_band = _compute_risk_band(_extract_query_text(request), status, citations, None)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "tool_path",
                "sources": sources,
                "citations": citations,
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        yield _sse_event("delta", {"delta": str(answer.get("content") or "")})
        yield _sse_event(
            "done",
            {
                "status": status,
                "citations": citations,
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_COMPLETED",
            trace_id=trace_id,
            route="TOOL_PATH",
            reason_code=reason_code,
            payload={"status": status, "citation_count": len(citations)},
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "tool_path"})
        return

    prepared = await _prepare_chat(request, trace_id, request_id, session_id=session_id, user_id=user_id)
    if not prepared.get("ok"):
        response = prepared.get("response") or _fallback(
            trace_id,
            request_id,
            None,
            "RAG_NO_CHUNKS",
            session_id=session_id,
            user_id=user_id,
        )
        answer = response.get("answer", {}).get("content") if isinstance(response.get("answer"), dict) else ""
        reason_code = str(response.get("reason_code") or "RAG_NO_CHUNKS")
        recoverable = bool(response.get("recoverable")) if isinstance(response.get("recoverable"), bool) else True
        next_action = str(response.get("next_action") or "REFINE_QUERY")
        retry_after_ms = response.get("retry_after_ms")
        fallback_count = response.get("fallback_count")
        escalated = bool(response.get("escalated")) if isinstance(response.get("escalated"), bool) else False
        risk_band = _compute_risk_band("", response.get("status", "insufficient_evidence"), [], "RAG_NO_CHUNKS")
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "fallback",
                "sources": [],
                "citations": [],
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        yield _sse_event("delta", {"delta": answer})
        yield _sse_event(
            "done",
            {
                "status": response.get("status", "insufficient_evidence"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": reason_code,
                "recoverable": recoverable,
                "next_action": next_action,
                "retry_after_ms": retry_after_ms,
                "fallback_count": fallback_count,
                "escalated": escalated,
            },
        )
        _save_unresolved_context(
            session_id,
            query_text,
            str(reason_code or str(prepared.get("reason") or "RAG_NO_CHUNKS")),
            trace_id=trace_id,
            request_id=request_id,
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    query = prepared.get("query") or ""
    canonical_key = prepared.get("canonical_key")
    locale = prepared.get("locale")
    selected = prepared.get("selected") or []
    sources = _format_sources(selected)
    answer_cache_key = _answer_cache_key(canonical_key, locale)

    if _answer_cache_enabled():
        cached = _CACHE.get_json(answer_cache_key)
        if isinstance(cached, dict) and isinstance(cached.get("response"), dict):
            cached_response = cached.get("response")
            cached_answer = cached_response.get("answer") if isinstance(cached_response.get("answer"), dict) else {}
            cached_citations = [str(item) for item in (cached_response.get("citations") or []) if isinstance(item, str)]
            cached_status = str(cached_response.get("status") or "ok")
            cached_reason_code = str(cached_response.get("reason_code") or "OK")
            cached_recoverable = (
                bool(cached_response.get("recoverable")) if isinstance(cached_response.get("recoverable"), bool) else False
            )
            cached_next_action = str(cached_response.get("next_action") or "NONE")
            cached_retry_after_ms = cached_response.get("retry_after_ms")
            cached_fallback_count = cached_response.get("fallback_count")
            cached_escalated = bool(cached_response.get("escalated")) if isinstance(cached_response.get("escalated"), bool) else False
            risk_band = _compute_risk_band(query, cached_status, cached_citations, None)
            yield _sse_event(
                "meta",
                {
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "status": "cached",
                    "sources": sources,
                    "citations": cached_citations,
                    "risk_band": risk_band,
                    "reason_code": cached_reason_code,
                    "recoverable": cached_recoverable,
                    "next_action": cached_next_action,
                    "retry_after_ms": cached_retry_after_ms,
                    "fallback_count": cached_fallback_count,
                    "escalated": cached_escalated,
                },
            )
            yield _sse_event("delta", {"delta": cached_answer.get("content") or ""})
            yield _sse_event(
                "done",
                {
                    "status": cached_status,
                    "citations": cached_citations,
                    "risk_band": risk_band,
                    "reason_code": cached_reason_code,
                    "recoverable": cached_recoverable,
                    "next_action": cached_next_action,
                    "retry_after_ms": cached_retry_after_ms,
                    "fallback_count": cached_fallback_count,
                    "escalated": cached_escalated,
                },
            )
            _reset_fallback_count(session_id)
            _clear_unresolved_context(session_id)
            _remember_episode_memory_fact(
                user_id=user_id,
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                request_id=request_id,
                opted_in=memory_opt_in,
            )
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "answer_cache_hit"})
            return

    semantic_cached = _semantic_cache_lookup(query, str(locale), trace_id, request_id)
    if isinstance(semantic_cached, dict):
        semantic_answer = semantic_cached.get("answer") if isinstance(semantic_cached.get("answer"), dict) else {}
        semantic_citations = [str(item) for item in (semantic_cached.get("citations") or []) if isinstance(item, str)]
        semantic_status = str(semantic_cached.get("status") or "ok")
        semantic_reason_code = str(semantic_cached.get("reason_code") or "OK")
        semantic_recoverable = bool(semantic_cached.get("recoverable")) if isinstance(semantic_cached.get("recoverable"), bool) else False
        semantic_next_action = str(semantic_cached.get("next_action") or "NONE")
        semantic_retry_after_ms = semantic_cached.get("retry_after_ms")
        semantic_fallback_count = semantic_cached.get("fallback_count")
        semantic_escalated = bool(semantic_cached.get("escalated")) if isinstance(semantic_cached.get("escalated"), bool) else False
        risk_band = _compute_risk_band(query, semantic_status, semantic_citations, None)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "cached_semantic",
                "sources": semantic_cached.get("sources") if isinstance(semantic_cached.get("sources"), list) else sources,
                "citations": semantic_citations,
                "risk_band": risk_band,
                "reason_code": semantic_reason_code,
                "recoverable": semantic_recoverable,
                "next_action": semantic_next_action,
                "retry_after_ms": semantic_retry_after_ms,
                "fallback_count": semantic_fallback_count,
                "escalated": semantic_escalated,
            },
        )
        yield _sse_event("delta", {"delta": semantic_answer.get("content") or ""})
        yield _sse_event(
            "done",
            {
                "status": semantic_status,
                "citations": semantic_citations,
                "risk_band": risk_band,
                "reason_code": semantic_reason_code,
                "recoverable": semantic_recoverable,
                "next_action": semantic_next_action,
                "retry_after_ms": semantic_retry_after_ms,
                "fallback_count": semantic_fallback_count,
                "escalated": semantic_escalated,
            },
        )
        _reset_fallback_count(session_id)
        _clear_unresolved_context(session_id)
        _remember_episode_memory_fact(
            user_id=user_id,
            session_id=session_id,
            query_text=query_text,
            trace_id=trace_id,
            request_id=request_id,
            opted_in=memory_opt_in,
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "semantic_cache_hit"})
        return

    payload = _build_llm_payload(
        request,
        trace_id,
        request_id,
        query,
        selected,
        memory_facts=memory_facts,
    )
    admission_reason = _admission_block_reason(payload, mode="stream")
    if admission_reason:
        metrics.inc("chat_admission_block_total", {"reason": admission_reason, "mode": "stream"})
        fallback_response = _fallback(trace_id, request_id, None, admission_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            admission_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], admission_reason)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "fallback",
                "sources": [],
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        yield _sse_event("delta", {"delta": str(fallback_response.get("answer", {}).get("content") if isinstance(fallback_response.get("answer"), dict) else "")})
        yield _sse_event(
            "done",
            {
                "status": fallback_response.get("status"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_BLOCKED",
            trace_id=trace_id,
            route="ADMISSION",
            reason_code=admission_reason,
            payload={"stream": True},
        )
        _append_action_audit_safe(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type="LLM_ADMISSION_BLOCK",
            reason_code=admission_reason,
            metadata={"mode": "stream"},
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    call_budget_reason = _reserve_llm_call_budget(session_id, user_id, mode="stream")
    if call_budget_reason:
        metrics.inc("chat_admission_block_total", {"reason": call_budget_reason, "mode": "stream"})
        fallback_response = _fallback(trace_id, request_id, None, call_budget_reason, session_id=session_id, user_id=user_id)
        _save_unresolved_context(
            session_id,
            query,
            call_budget_reason,
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
        )
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], call_budget_reason)
        yield _sse_event(
            "meta",
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "status": "fallback",
                "sources": [],
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        yield _sse_event("delta", {"delta": str(fallback_response.get("answer", {}).get("content") if isinstance(fallback_response.get("answer"), dict) else "")})
        yield _sse_event(
            "done",
            {
                "status": fallback_response.get("status"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _append_turn_event_safe(
            session_id,
            request_id,
            "TURN_BLOCKED",
            trace_id=trace_id,
            route="ADMISSION",
            reason_code=call_budget_reason,
            payload={"stream": True},
        )
        _append_action_audit_safe(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type="LLM_ADMISSION_BLOCK",
            reason_code=call_budget_reason,
            metadata={"mode": "stream"},
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    if not _llm_stream_enabled():
        try:
            data = await _call_llm_json(payload, trace_id, request_id)
            answer_text = str(data.get("content") or "")
            raw_citations = data.get("citations") if isinstance(data.get("citations"), list) else _extract_citations_from_text(answer_text)
            citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
            if not citations:
                yield _sse_event("error", {"code": "LLM_NO_CITATIONS", "message": "근거 문서 매핑에 실패했습니다."})
                risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_NO_CITATIONS")
                fallback_response = _fallback(
                    trace_id,
                    request_id,
                    None,
                    "LLM_NO_CITATIONS",
                    session_id=session_id,
                    user_id=user_id,
                )
                yield _sse_event(
                    "done",
                    {
                        "status": "insufficient_evidence",
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": fallback_response.get("reason_code"),
                        "recoverable": fallback_response.get("recoverable"),
                        "next_action": fallback_response.get("next_action"),
                        "retry_after_ms": fallback_response.get("retry_after_ms"),
                        "fallback_count": fallback_response.get("fallback_count"),
                        "escalated": fallback_response.get("escalated"),
                    },
                )
                _save_unresolved_context(session_id, query, "LLM_NO_CITATIONS", trace_id=trace_id, request_id=request_id)
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return
            coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
            if not coverage_ok:
                metrics.inc(
                    "chat_citation_coverage_block_total",
                    {
                        "risk": "high" if _is_high_risk_query(query) else "normal",
                        "threshold": f"{coverage_threshold:.2f}",
                    },
                )
                yield _sse_event("error", {"code": "LLM_LOW_CITATION_COVERAGE", "message": "근거 커버리지가 부족합니다."})
                risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_LOW_CITATION_COVERAGE")
                fallback_response = _fallback(
                    trace_id,
                    request_id,
                    None,
                    "LLM_LOW_CITATION_COVERAGE",
                    session_id=session_id,
                    user_id=user_id,
                )
                yield _sse_event(
                    "done",
                    {
                        "status": "insufficient_evidence",
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": fallback_response.get("reason_code"),
                        "recoverable": fallback_response.get("recoverable"),
                        "next_action": fallback_response.get("next_action"),
                        "retry_after_ms": fallback_response.get("retry_after_ms"),
                        "fallback_count": fallback_response.get("fallback_count"),
                        "escalated": fallback_response.get("escalated"),
                    },
                )
                _save_unresolved_context(session_id, query, "LLM_LOW_CITATION_COVERAGE", trace_id=trace_id, request_id=request_id)
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return

            guarded_response, guard_reason = _guard_answer(
                query,
                answer_text,
                citations,
                trace_id,
                request_id,
                session_id=session_id,
                user_id=user_id,
            )
            if guarded_response is not None:
                metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
                risk_band = _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)
                yield _sse_event(
                    "meta",
                    {
                        "trace_id": trace_id,
                        "request_id": request_id,
                        "status": "guard_blocked",
                        "sources": sources,
                        "citations": [],
                        "risk_band": risk_band,
                    },
                )
                yield _sse_event(
                    "error",
                    {"code": guard_reason or "OUTPUT_GUARD_BLOCKED", "message": _guard_blocked_message()},
                )
                yield _sse_event(
                    "done",
                    {
                        "status": guarded_response.get("status", "insufficient_evidence"),
                        "citations": [],
                        "risk_band": risk_band,
                        "reason_code": guarded_response.get("reason_code"),
                        "recoverable": guarded_response.get("recoverable"),
                        "next_action": guarded_response.get("next_action"),
                        "retry_after_ms": guarded_response.get("retry_after_ms"),
                        "fallback_count": guarded_response.get("fallback_count"),
                        "escalated": guarded_response.get("escalated"),
                    },
                )
                _save_unresolved_context(
                    session_id,
                    query,
                    str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
                    trace_id=trace_id,
                    request_id=request_id,
                )
                metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
                metrics.inc("chat_requests_total", {"decision": "fallback"})
                return

            risk_band = _compute_risk_band(query, "ok", citations, None)
            metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
            yield _sse_event(
                "meta",
                {
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "status": "ok",
                    "sources": sources,
                    "citations": citations,
                    "risk_band": risk_band,
                "reason_code": "OK",
                "recoverable": False,
                "next_action": "NONE",
                "retry_after_ms": None,
                "fallback_count": 0,
                "escalated": False,
            },
        )
            yield _sse_event("delta", {"delta": answer_text})
            yield _sse_event(
                "done",
                {
                    "status": "ok",
                    "citations": citations,
                    "risk_band": risk_band,
                    "reason_code": "OK",
                    "recoverable": False,
                    "next_action": "NONE",
                    "retry_after_ms": None,
                    "fallback_count": 0,
                    "escalated": False,
                },
            )
            response = {
                "version": "v1",
                "trace_id": trace_id,
                "request_id": request_id,
                "answer": {"role": "assistant", "content": answer_text},
                "sources": _format_sources(selected),
                "citations": citations,
                "status": "ok",
                "reason_code": "OK",
                "recoverable": False,
                "next_action": "NONE",
                "retry_after_ms": None,
                "fallback_count": 0,
                "escalated": False,
            }
            if _answer_cache_enabled():
                _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))
            _semantic_cache_store(query, str(locale), response)
            _reset_fallback_count(session_id)
            _clear_unresolved_context(session_id)
            _remember_episode_memory_fact(
                user_id=user_id,
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                request_id=request_id,
                opted_in=memory_opt_in,
            )
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "ok"})
            return
        except Exception:
            yield _sse_event("error", {"code": "PROVIDER_TIMEOUT", "message": "LLM 응답 지연으로 처리하지 못했습니다."})
            risk_band = _compute_risk_band(query, "error", [], "PROVIDER_TIMEOUT")
            _record_chat_timeout("llm_generate")
            fallback_response = _fallback(
                trace_id,
                request_id,
                None,
                "PROVIDER_TIMEOUT",
                session_id=session_id,
                user_id=user_id,
            )
            yield _sse_event(
                "done",
                {
                    "status": "error",
                    "citations": [],
                    "risk_band": risk_band,
                    "reason_code": fallback_response.get("reason_code"),
                    "recoverable": fallback_response.get("recoverable"),
                    "next_action": fallback_response.get("next_action"),
                    "retry_after_ms": fallback_response.get("retry_after_ms"),
                    "fallback_count": fallback_response.get("fallback_count"),
                    "escalated": fallback_response.get("escalated"),
                },
            )
            _save_unresolved_context(session_id, query, "PROVIDER_TIMEOUT", trace_id=trace_id, request_id=request_id)
            metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
            metrics.inc("chat_requests_total", {"decision": "fallback"})
            return

    yield _sse_event(
        "meta",
        {
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "streaming",
            "sources": sources,
            "citations": [],
            "reason_code": "IN_PROGRESS",
            "recoverable": True,
            "next_action": "WAIT",
            "retry_after_ms": None,
            "fallback_count": None,
            "escalated": False,
        },
    )
    stream_iter, stream_state = await _stream_llm(payload, trace_id, request_id)
    async for event in stream_iter:
        if event.startswith("event: done"):
            continue
        if event.startswith("event: meta"):
            continue
        yield event

    if stream_state.get("llm_error"):
        risk_band = _compute_risk_band(query, "error", [], "PROVIDER_TIMEOUT")
        _record_chat_timeout("llm_stream")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "PROVIDER_TIMEOUT",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "error",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "PROVIDER_TIMEOUT", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    answer_text = stream_state.get("answer") or ""
    raw_citations = stream_state.get("citations") or _extract_citations_from_text(answer_text)
    citations = _validate_citations([str(item) for item in raw_citations if isinstance(item, str)], selected)
    if not citations:
        metrics.inc("chat_fallback_total", {"reason": "LLM_NO_CITATIONS"})
        yield _sse_event("error", {"code": "LLM_NO_CITATIONS", "message": "근거 문서 매핑에 실패했습니다."})
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_NO_CITATIONS")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "LLM_NO_CITATIONS",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "insufficient_evidence",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "LLM_NO_CITATIONS", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return
    coverage_ok, coverage, coverage_threshold = _is_citation_coverage_sufficient(query, citations, selected)
    if not coverage_ok:
        metrics.inc(
            "chat_citation_coverage_block_total",
            {
                "risk": "high" if _is_high_risk_query(query) else "normal",
                "threshold": f"{coverage_threshold:.2f}",
            },
        )
        yield _sse_event("error", {"code": "LLM_LOW_CITATION_COVERAGE", "message": "근거 커버리지가 부족합니다."})
        risk_band = _compute_risk_band(query, "insufficient_evidence", [], "LLM_LOW_CITATION_COVERAGE")
        fallback_response = _fallback(
            trace_id,
            request_id,
            None,
            "LLM_LOW_CITATION_COVERAGE",
            session_id=session_id,
            user_id=user_id,
        )
        yield _sse_event(
            "done",
            {
                "status": "insufficient_evidence",
                "citations": [],
                "risk_band": risk_band,
                "reason_code": fallback_response.get("reason_code"),
                "recoverable": fallback_response.get("recoverable"),
                "next_action": fallback_response.get("next_action"),
                "retry_after_ms": fallback_response.get("retry_after_ms"),
                "fallback_count": fallback_response.get("fallback_count"),
                "escalated": fallback_response.get("escalated"),
            },
        )
        _save_unresolved_context(session_id, query, "LLM_LOW_CITATION_COVERAGE", trace_id=trace_id, request_id=request_id)
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    guarded_response, guard_reason = _guard_answer(
        query,
        answer_text,
        citations,
        trace_id,
        request_id,
        session_id=session_id,
        user_id=user_id,
    )
    if guarded_response is not None:
        metrics.inc("chat_output_guard_total", {"result": "blocked", "reason": guard_reason or "unknown"})
        risk_band = _compute_risk_band(query, guarded_response.get("status", "insufficient_evidence"), [], guard_reason)
        yield _sse_event(
            "error",
            {"code": guard_reason or "OUTPUT_GUARD_BLOCKED", "message": _guard_blocked_message()},
        )
        yield _sse_event(
            "done",
            {
                "status": guarded_response.get("status", "insufficient_evidence"),
                "citations": [],
                "risk_band": risk_band,
                "reason_code": guarded_response.get("reason_code"),
                "recoverable": guarded_response.get("recoverable"),
                "next_action": guarded_response.get("next_action"),
                "retry_after_ms": guarded_response.get("retry_after_ms"),
                "fallback_count": guarded_response.get("fallback_count"),
                "escalated": guarded_response.get("escalated"),
            },
        )
        _save_unresolved_context(
            session_id,
            query,
            str(guarded_response.get("reason_code") or guard_reason or "OUTPUT_GUARD_BLOCKED"),
            trace_id=trace_id,
            request_id=request_id,
        )
        metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
        metrics.inc("chat_requests_total", {"decision": "fallback"})
        return

    response = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {"role": "assistant", "content": answer_text},
        "sources": _format_sources(selected),
        "citations": citations,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
    }
    if _answer_cache_enabled():
        _CACHE.set_json(answer_cache_key, {"response": response}, ttl=max(1, _answer_cache_ttl_sec()))

    final_status = stream_state.get("done_status") or "ok"
    risk_band = _compute_risk_band(query, final_status, citations, None)
    metrics.inc("chat_output_guard_total", {"result": "pass", "reason": "ok"})
    metrics.inc("chat_answer_risk_band_total", {"band": risk_band})
    _reset_fallback_count(session_id)
    _clear_unresolved_context(session_id)
    _remember_episode_memory_fact(
        user_id=user_id,
        session_id=session_id,
        query_text=query_text,
        trace_id=trace_id,
        request_id=request_id,
        opted_in=memory_opt_in,
    )
    yield _sse_event(
        "done",
        {
            "status": final_status,
            "citations": citations,
            "risk_band": risk_band,
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "fallback_count": 0,
            "escalated": False,
        },
    )
    metrics.inc("chat_requests_total", {"decision": "ok"})


async def run_chat(request: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    rollout = _select_rollout_engine(request, request_id)
    effective_engine = str(rollout.get("effective_engine") or "agent")
    allow_tools = effective_engine == "agent"
    response = await _run_chat_impl(
        request,
        trace_id,
        request_id,
        allow_tools=allow_tools,
    )
    _record_rollout_gate(effective_engine, response)
    if bool(rollout.get("shadow_enabled")):
        try:
            shadow_signature = await _shadow_agent_signature(request, trace_id, f"{request_id}:shadow")
            _record_shadow_diff(response, shadow_signature)
        except Exception:
            metrics.inc("chat_rollout_shadow_diff_total", {"result": "error"})
    return response


async def run_chat_stream(request: Dict[str, Any], trace_id: str, request_id: str) -> AsyncIterator[str]:
    rollout = _select_rollout_engine(request, request_id)
    effective_engine = str(rollout.get("effective_engine") or "agent")
    allow_tools = effective_engine == "agent"
    if bool(rollout.get("shadow_enabled")):
        async def _shadow_probe() -> None:
            try:
                await _shadow_agent_signature(request, trace_id, f"{request_id}:shadow")
                metrics.inc("chat_rollout_shadow_diff_total", {"result": "stream_observed"})
            except Exception:
                metrics.inc("chat_rollout_shadow_diff_total", {"result": "error"})

        asyncio.create_task(_shadow_probe())
    async for event in _run_chat_stream_impl(
        request,
        trace_id,
        request_id,
        allow_tools=allow_tools,
    ):
        yield event


async def explain_chat_rag(request: Dict[str, Any], trace_id: str, request_id: str) -> Dict[str, Any]:
    query = _extract_query_text(request)
    if not query.strip():
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "error",
            "reason_codes": ["NO_MESSAGES"],
            "query": {"text": ""},
            "retrieval": {"lexical": [], "vector": [], "fused": [], "selected": []},
        }

    locale = _locale_from_request(request)
    canonical_key = _canonical_key(query, locale)
    trace, rewrite_meta = await _retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id)

    reason_codes = list(trace.get("reason_codes") or [])
    if rewrite_meta.get("rewrite_applied"):
        reason_codes.append("REWRITE_APPLIED")
    if rewrite_meta.get("rewrite_reason"):
        reason_codes.append(str(rewrite_meta.get("rewrite_reason")))
    selected = trace.get("selected") or []
    debug_payload = _build_llm_payload(request, trace_id, request_id, rewrite_meta.get("rewritten_query") or query, selected)
    llm_routing = _preview_provider_routing(debug_payload, mode="json")

    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "query": {
            "text": query,
            "locale": locale,
            "canonical_key": canonical_key,
            "rewritten": rewrite_meta.get("rewritten_query"),
        },
        "rewrite": rewrite_meta,
        "retrieval": {
            "top_n": trace.get("top_n"),
            "top_k": trace.get("top_k"),
            "lexical": trace.get("lexical") or [],
            "vector": trace.get("vector") or [],
            "fused": trace.get("fused") or [],
            "selected": trace.get("selected") or [],
            "rerank": trace.get("rerank") or {},
            "took_ms": trace.get("took_ms") or 0,
            "degraded": bool(trace.get("degraded")),
        },
        "llm_routing": llm_routing,
        "reason_codes": reason_codes,
    }


def get_chat_provider_snapshot(trace_id: str, request_id: str) -> Dict[str, Any]:
    providers = _llm_provider_chain()
    preview = _preview_provider_routing(
        {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "messages": [{"role": "user", "content": ""}],
            "context": {"chunks": []},
            "citations_required": True,
        },
        mode="json",
    )
    details: List[Dict[str, Any]] = []
    for name, url in providers:
        details.append(
            {
                "name": name,
                "url": url,
                "cooldown": _is_provider_unhealthy(name),
                "stats": _provider_stats_view(name),
            }
        )
    return {
        "routing": preview,
        "providers": details,
        "config": {
            "forced_provider": _llm_forced_provider() or None,
            "blocklist": sorted(_llm_provider_blocklist()),
            "health_routing_enabled": _llm_health_routing_enabled(),
            "health_min_sample": _llm_health_min_sample(),
            "cost_steering_enabled": _llm_cost_steering_enabled(),
            "low_cost_provider": _llm_low_cost_provider() or None,
            "intent_policy": _llm_provider_by_intent(),
        },
    }


def _semantic_cache_snapshot() -> Dict[str, Any]:
    disable = _CACHE.get_json(_semantic_cache_disable_key())
    drift = _CACHE.get_json(_semantic_cache_drift_key())
    now_ts = int(time.time())
    disabled_until = int(disable.get("until_ts") or 0) if isinstance(disable, dict) else 0
    drift_total = int(drift.get("total") or 0) if isinstance(drift, dict) else 0
    drift_errors = int(drift.get("errors") or 0) if isinstance(drift, dict) else 0
    drift_rate = float(drift.get("error_rate") or 0.0) if isinstance(drift, dict) else 0.0
    return {
        "enabled": _semantic_cache_enabled(),
        "policy_topic_version": _semantic_cache_policy_version(),
        "auto_disabled": disabled_until > now_ts,
        "disabled_until": disabled_until if disabled_until > now_ts else None,
        "disable_reason": str(disable.get("reason") or "") if isinstance(disable, dict) and disabled_until > now_ts else None,
        "similarity_threshold": _semantic_cache_similarity_threshold(),
        "drift_total": max(0, drift_total),
        "drift_errors": max(0, drift_errors),
        "drift_error_rate": max(0.0, drift_rate),
        "drift_max_error_rate": _semantic_cache_drift_max_error_rate(),
    }


def get_chat_session_state(session_id: str, trace_id: str, request_id: str) -> Dict[str, Any]:
    if not _is_valid_session_id(session_id):
        raise ValueError("invalid_session_id")

    durable_state = get_durable_chat_session_state(session_id)
    fallback_count: int
    if isinstance(durable_state, dict) and isinstance(durable_state.get("fallback_count"), int):
        fallback_count = max(0, int(durable_state.get("fallback_count")))
    else:
        fallback_count = _load_fallback_count(session_id)
    threshold = _fallback_escalation_threshold()
    escalation_ready = fallback_count >= threshold
    unresolved = None
    if isinstance(durable_state, dict):
        candidate = durable_state.get("unresolved_context")
        if isinstance(candidate, dict):
            unresolved = candidate
    if unresolved is None:
        unresolved = _load_unresolved_context(session_id)
    unresolved_context: Optional[Dict[str, Any]] = None
    recommended_action = "NONE"
    recommended_message = "현재 챗봇 세션 상태는 정상입니다."
    if isinstance(unresolved, dict):
        reason_code = str(unresolved.get("reason_code") or "")
        defaults = _fallback_defaults(reason_code)
        unresolved_context = {
            "reason_code": reason_code,
            "reason_message": str(defaults.get("message") or ""),
            "next_action": str(defaults.get("next_action") or "RETRY"),
            "trace_id": str(unresolved.get("trace_id") or ""),
            "request_id": str(unresolved.get("request_id") or ""),
            "updated_at": int(unresolved.get("updated_at") or 0),
            "query_preview": _query_preview(str(unresolved.get("query") or "")),
        }
        recommended_action = str(defaults.get("next_action") or "RETRY")
        recommended_message = str(defaults.get("message") or "직전 미해결 사유를 확인해 주세요.")
    if escalation_ready:
        recommended_action = "OPEN_SUPPORT_TICKET"
        recommended_message = "반복 실패가 임계치를 초과했습니다. 상담 티켓 접수를 권장합니다."
    selection_snapshot: Optional[Dict[str, Any]] = None
    pending_action_snapshot: Optional[Dict[str, Any]] = None
    if isinstance(durable_state, dict):
        selection = durable_state.get("selection")
        if isinstance(selection, dict):
            last_candidates = selection.get("last_candidates")
            selected_book = selection.get("selected_book") if isinstance(selection.get("selected_book"), dict) else {}
            selection_snapshot = {
                "type": str(selection.get("type") or ""),
                "candidates_count": len(last_candidates) if isinstance(last_candidates, list) else 0,
                "selected_index": selection.get("selected_index") if isinstance(selection.get("selected_index"), int) else None,
                "selected_title": str(selected_book.get("title") or "") or None,
                "selected_isbn": str(selected_book.get("isbn") or "") or None,
            }
        pending_action = durable_state.get("pending_action")
        if isinstance(pending_action, dict):
            pending_action_snapshot = {
                "type": str(pending_action.get("type") or ""),
                "state": str(pending_action.get("state") or ""),
                "expires_at": pending_action.get("expires_at"),
            }
    llm_budget_snapshot = _load_llm_call_budget_snapshot(session_id, _session_user_from_session_id(session_id))
    semantic_snapshot = _semantic_cache_snapshot()
    episode_snapshot = _episode_memory_snapshot(_session_user_from_session_id(session_id))
    recommend_snapshot = get_recommend_experiment_snapshot()
    return {
        "session_id": session_id,
        "state_version": int(durable_state.get("state_version")) if isinstance(durable_state, dict) and isinstance(durable_state.get("state_version"), int) else None,
        "last_turn_id": str(durable_state.get("last_turn_id")) if isinstance(durable_state, dict) and durable_state.get("last_turn_id") is not None else None,
        "fallback_count": fallback_count,
        "fallback_escalation_threshold": threshold,
        "escalation_ready": escalation_ready,
        "recommended_action": recommended_action,
        "recommended_message": recommended_message,
        "unresolved_context": unresolved_context,
        "selection_snapshot": selection_snapshot,
        "pending_action_snapshot": pending_action_snapshot,
        "llm_call_budget": llm_budget_snapshot,
        "semantic_cache": semantic_snapshot,
        "episode_memory": episode_snapshot,
        "recommend_experiment": recommend_snapshot,
        "trace_id": trace_id,
        "request_id": request_id,
    }


def reset_chat_session_state(session_id: str, trace_id: str, request_id: str) -> Dict[str, Any]:
    if not _is_valid_session_id(session_id):
        raise ValueError("invalid_session_id")
    reset_user_id = _session_user_from_session_id(session_id)
    previous_fallback_count = _load_fallback_count(session_id)
    previous_unresolved_context = isinstance(_load_unresolved_context(session_id), dict)
    previous_llm_call_count = _load_llm_call_budget_count(session_id, reset_user_id)
    previous_episode_memory_count = len(_load_episode_memory_entries(reset_user_id))
    _reset_fallback_count(session_id, trace_id=trace_id, request_id=request_id)
    _clear_unresolved_context(session_id, trace_id=trace_id, request_id=request_id)
    _clear_llm_call_budget(session_id, reset_user_id)
    deleted_episode_memory_count = _delete_episode_memory(reset_user_id)
    episode_memory_cleared = bool(reset_user_id)
    _append_action_audit_safe(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type="SESSION_RESET",
        reason_code="MANUAL_RESET",
        metadata={
            "previous_fallback_count": previous_fallback_count,
            "previous_unresolved_context": previous_unresolved_context,
            "previous_llm_call_count": previous_llm_call_count,
            "previous_episode_memory_count": previous_episode_memory_count,
            "deleted_episode_memory_count": deleted_episode_memory_count,
            "episode_memory_cleared": episode_memory_cleared,
        },
    )
    _append_turn_event_safe(
        session_id,
        request_id,
        "SESSION_RESET",
        trace_id=trace_id,
        route="RESET",
        reason_code="MANUAL_RESET",
        payload={
            "previous_fallback_count": previous_fallback_count,
            "previous_unresolved_context": previous_unresolved_context,
            "previous_llm_call_count": previous_llm_call_count,
            "previous_episode_memory_count": previous_episode_memory_count,
            "deleted_episode_memory_count": deleted_episode_memory_count,
            "episode_memory_cleared": episode_memory_cleared,
        },
    )
    reset_ticket_session_context(session_id)
    durable_state = get_durable_chat_session_state(session_id)
    return {
        "session_id": session_id,
        "reset_applied": True,
        "previous_fallback_count": previous_fallback_count,
        "previous_unresolved_context": previous_unresolved_context,
        "previous_llm_call_count": previous_llm_call_count,
        "previous_episode_memory_count": previous_episode_memory_count,
        "episode_memory_cleared": episode_memory_cleared,
        "state_version": int(durable_state.get("state_version")) if isinstance(durable_state, dict) and isinstance(durable_state.get("state_version"), int) else None,
        "reset_at_ms": int(time.time() * 1000),
        "trace_id": trace_id,
        "request_id": request_id,
    }
