#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

RISK_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
MODE_ORDER: dict[str, int] = {"NORMAL": 0, "SOFT_CLAMP": 1, "HARD_CLAMP": 2}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_ts(row: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _intent(row: Mapping[str, Any]) -> str:
    text = str(row.get("intent") or "UNKNOWN").strip().upper()
    return text if text else "UNKNOWN"


def _normalize_risk(raw: Any, *, intent: str) -> str:
    text = str(raw or "").strip().upper()
    alias = {
        "LOW_RISK": "LOW",
        "MEDIUM_RISK": "MEDIUM",
        "MID": "MEDIUM",
        "HIGH_RISK": "HIGH",
        "CRITICAL": "HIGH",
    }
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return text
    if text in alias:
        return alias[text]

    heuristic_high = {"REFUND_REQUEST", "CANCEL_ORDER", "ADDRESS_CHANGE", "PAYMENT_CHANGE"}
    heuristic_medium = {"ORDER_STATUS", "DELIVERY_TRACKING", "EXCHANGE_REQUEST"}
    if intent in heuristic_high:
        return "HIGH"
    if intent in heuristic_medium:
        return "MEDIUM"
    return "LOW"


def read_events(path: Path, *, window_days: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = (now or datetime.now(timezone.utc)) - timedelta(days=max(1, int(window_days)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def infer_budget_utilization(events: list[Mapping[str, Any]], *, override: float | None = None) -> float:
    if override is not None and override >= 0.0:
        return max(0.0, float(override))

    ratios: list[float] = []
    for row in events:
        for key in ("budget_utilization", "budget_ratio", "budget_usage_ratio"):
            if row.get(key) is not None:
                ratios.append(max(0.0, _safe_float(row.get(key), 0.0)))
        spent = _safe_float(row.get("budget_spent_usd"), -1.0)
        limit = _safe_float(row.get("budget_limit_usd"), -1.0)
        if spent >= 0.0 and limit > 0.0:
            ratios.append(max(0.0, spent / limit))
    if not ratios:
        return 0.0
    return max(ratios)


def summarize_cost_events(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    resolved_total = 0
    unresolved_total = 0
    resolved_cost_usd = 0.0
    unresolved_cost_usd = 0.0
    total_tool_calls = 0
    total_rewrite_steps = 0
    heavy_route_total = 0
    light_route_total = 0

    by_intent: dict[str, dict[str, Any]] = {}

    for row in events:
        intent = _intent(row)
        risk = _normalize_risk(row.get("risk_level") or row.get("risk_tier"), intent=intent)
        resolved = _safe_bool(row.get("resolved"), False)
        cost_usd = max(0.0, _safe_float(row.get("session_cost_usd"), _safe_float(row.get("cost_usd"), 0.0)))
        tool_calls = max(0, _safe_int(row.get("tool_calls"), 0))
        rewrite_steps = max(
            0,
            _safe_int(
                row.get("rewrite_steps"),
                _safe_int(row.get("rewrite_count"), 0),
            ),
        )
        route_profile = str(row.get("route_profile") or row.get("route_mode") or "").strip().upper()

        total_tool_calls += tool_calls
        total_rewrite_steps += rewrite_steps
        if route_profile in {"HEAVY", "TRUSTED"}:
            heavy_route_total += 1
        if route_profile == "LIGHT":
            light_route_total += 1

        row_intent = by_intent.setdefault(
            intent,
            {
                "window_size": 0,
                "resolved_total": 0,
                "unresolved_total": 0,
                "resolved_cost_usd": 0.0,
                "unresolved_cost_usd": 0.0,
                "tool_calls_total": 0,
                "rewrite_steps_total": 0,
                "risk_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0},
            },
        )
        row_intent["window_size"] += 1
        row_intent["tool_calls_total"] += tool_calls
        row_intent["rewrite_steps_total"] += rewrite_steps
        row_intent["risk_counts"][risk] = int(row_intent["risk_counts"].get(risk) or 0) + 1

        if resolved:
            resolved_total += 1
            resolved_cost_usd += cost_usd
            row_intent["resolved_total"] += 1
            row_intent["resolved_cost_usd"] += cost_usd
        else:
            unresolved_total += 1
            unresolved_cost_usd += cost_usd
            row_intent["unresolved_total"] += 1
            row_intent["unresolved_cost_usd"] += cost_usd

    window_size = len(events)
    total_cost_usd = resolved_cost_usd + unresolved_cost_usd
    resolution_rate = 0.0 if window_size == 0 else float(resolved_total) / float(window_size)
    cost_per_resolved_session = 0.0 if resolved_total == 0 else resolved_cost_usd / float(resolved_total)

    intent_rows: list[dict[str, Any]] = []
    for intent, row in sorted(by_intent.items(), key=lambda item: (-float(item[1]["resolved_cost_usd"] + item[1]["unresolved_cost_usd"]), item[0])):
        risk_counts = row.get("risk_counts") if isinstance(row.get("risk_counts"), Mapping) else {}
        risk_level = "LOW"
        for candidate in ("MEDIUM", "HIGH"):
            if int(risk_counts.get(candidate) or 0) > 0:
                risk_level = candidate
        resolved_cnt = int(row["resolved_total"])
        unresolved_cnt = int(row["unresolved_total"])
        intent_total = resolved_cnt + unresolved_cnt
        resolved_cost = float(row["resolved_cost_usd"])
        unresolved_cost = float(row["unresolved_cost_usd"])

        intent_rows.append(
            {
                "intent": intent,
                "risk_level": risk_level,
                "window_size": intent_total,
                "resolved_total": resolved_cnt,
                "unresolved_total": unresolved_cnt,
                "resolution_rate": 0.0 if intent_total == 0 else float(resolved_cnt) / float(intent_total),
                "cost_per_resolved_session": 0.0 if resolved_cnt == 0 else resolved_cost / float(resolved_cnt),
                "unresolved_cost_burn_total": unresolved_cost,
                "total_cost_usd": resolved_cost + unresolved_cost,
                "avg_tool_calls": 0.0 if intent_total == 0 else float(row["tool_calls_total"]) / float(intent_total),
                "avg_rewrite_steps": 0.0 if intent_total == 0 else float(row["rewrite_steps_total"]) / float(intent_total),
            }
        )

    return {
        "window_size": window_size,
        "resolved_total": resolved_total,
        "unresolved_total": unresolved_total,
        "resolution_rate": resolution_rate,
        "cost_per_resolved_session": cost_per_resolved_session,
        "total_cost_usd": total_cost_usd,
        "unresolved_cost_burn_total": unresolved_cost_usd,
        "avg_tool_calls": 0.0 if window_size == 0 else float(total_tool_calls) / float(window_size),
        "avg_rewrite_steps": 0.0 if window_size == 0 else float(total_rewrite_steps) / float(window_size),
        "heavy_route_ratio": 0.0 if window_size == 0 else float(heavy_route_total) / float(window_size),
        "light_route_ratio": 0.0 if window_size == 0 else float(light_route_total) / float(window_size),
        "intents": intent_rows,
    }


def decide_optimizer_policy(
    summary: Mapping[str, Any],
    *,
    budget_utilization: float,
    soft_budget_utilization: float,
    hard_budget_utilization: float,
    min_resolution_rate: float,
    max_cost_per_resolved_session: float,
    high_risk_intents: set[str],
) -> dict[str, Any]:
    mode = "NORMAL"
    if budget_utilization >= max(0.0, float(hard_budget_utilization)):
        mode = "HARD_CLAMP"
    elif budget_utilization >= max(0.0, float(soft_budget_utilization)):
        mode = "SOFT_CLAMP"

    intents = summary.get("intents") if isinstance(summary.get("intents"), list) else []
    policies: list[dict[str, Any]] = []
    estimated_savings_total = 0.0

    for row in intents:
        if not isinstance(row, Mapping):
            continue
        intent = str(row.get("intent") or "UNKNOWN").strip().upper() or "UNKNOWN"
        risk_level = _normalize_risk(row.get("risk_level"), intent=intent)
        resolved_total = max(0, _safe_int(row.get("resolved_total"), 0))
        resolution_rate = max(0.0, _safe_float(row.get("resolution_rate"), 0.0))
        cost_per_resolved = max(0.0, _safe_float(row.get("cost_per_resolved_session"), 0.0))

        route_policy = "BALANCED"
        action = "KEEP_BALANCED"
        reason = "baseline"
        savings_factor = 0.0

        if intent in high_risk_intents or risk_level == "HIGH":
            route_policy = "TRUSTED"
            action = "PRESERVE_HIGH_RISK"
            reason = "risk_guard"
        elif resolution_rate < max(0.0, float(min_resolution_rate)):
            route_policy = "TRUSTED"
            action = "QUALITY_PROTECT"
            reason = "resolution_below_threshold"
        elif mode == "SOFT_CLAMP":
            if risk_level == "LOW" and cost_per_resolved > max_cost_per_resolved_session:
                route_policy = "LIGHT"
                action = "SOFT_CLAMP_LOW_RISK"
                reason = "budget_pressure_soft"
                savings_factor = 0.25
            else:
                route_policy = "BALANCED"
                action = "SOFT_CLAMP_BALANCED"
                reason = "budget_pressure_soft"
        elif mode == "HARD_CLAMP":
            if risk_level == "LOW":
                route_policy = "LIGHT"
                action = "HARD_CLAMP_LOW_RISK"
                reason = "budget_pressure_hard"
                savings_factor = 0.40
            elif risk_level == "MEDIUM" and cost_per_resolved > max_cost_per_resolved_session:
                route_policy = "LIGHT"
                action = "HARD_CLAMP_MEDIUM_RISK"
                reason = "budget_pressure_hard"
                savings_factor = 0.20
            else:
                route_policy = "TRUSTED"
                action = "HARD_CLAMP_PRESERVE"
                reason = "budget_pressure_hard"
        elif cost_per_resolved > max_cost_per_resolved_session and risk_level == "LOW":
            route_policy = "BALANCED"
            action = "WATCH_HIGH_COST"
            reason = "cost_watch"

        estimated_savings_usd = max(0.0, (cost_per_resolved - max_cost_per_resolved_session)) * float(resolved_total) * savings_factor
        estimated_savings_total += estimated_savings_usd

        policies.append(
            {
                "intent": intent,
                "risk_level": risk_level,
                "route_policy": route_policy,
                "action": action,
                "reason": reason,
                "resolution_rate": resolution_rate,
                "cost_per_resolved_session": cost_per_resolved,
                "estimated_savings_usd": estimated_savings_usd,
            }
        )

    actions_by_mode: dict[str, list[str]] = {
        "NORMAL": [
            "기본 라우팅을 유지하고 고비용 저위험 intent만 감시합니다.",
        ],
        "SOFT_CLAMP": [
            "저위험 고비용 intent를 경량 경로로 전환하고 도구 반복을 제한합니다.",
            "중위험 intent는 품질 유지 우선으로 balanced 경로를 유지합니다.",
        ],
        "HARD_CLAMP": [
            "저위험 intent는 light 경로로 강등하고 고위험 intent는 trusted 경로를 고정합니다.",
            "예산 회복 전까지 heavy path admission을 제한합니다.",
        ],
    }

    return {
        "mode": mode,
        "budget_utilization": budget_utilization,
        "soft_budget_utilization": soft_budget_utilization,
        "hard_budget_utilization": hard_budget_utilization,
        "estimated_savings_total_usd": estimated_savings_total,
        "intent_policies": policies,
        "recommended_actions": actions_by_mode.get(mode, []),
        "preserve_high_risk_intents": sorted(high_risk_intents),
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    min_window: int,
    min_resolution_rate: float,
    soft_budget_utilization: float,
    hard_budget_utilization: float,
    require_clamp: bool,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    budget_utilization = _safe_float(decision.get("budget_utilization"), 0.0)
    mode = str(decision.get("mode") or "NORMAL").strip().upper()

    if window_size < max(0, int(min_window)):
        failures.append(f"cost optimizer window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if mode not in MODE_ORDER:
        failures.append(f"unknown optimizer mode: {mode}")
        return failures

    if budget_utilization >= max(0.0, float(hard_budget_utilization)) and mode != "HARD_CLAMP":
        failures.append(
            f"hard clamp required at budget utilization {budget_utilization:.4f}, but mode={mode}"
        )
    if require_clamp and budget_utilization >= max(0.0, float(soft_budget_utilization)) and mode == "NORMAL":
        failures.append(
            f"clamp required at budget utilization {budget_utilization:.4f}, but mode=NORMAL"
        )

    policies = decision.get("intent_policies") if isinstance(decision.get("intent_policies"), list) else []
    low_risk_light_total = 0
    for policy in policies:
        if not isinstance(policy, Mapping):
            continue
        intent = str(policy.get("intent") or "UNKNOWN").strip().upper() or "UNKNOWN"
        risk_level = _normalize_risk(policy.get("risk_level"), intent=intent)
        route_policy = str(policy.get("route_policy") or "BALANCED").strip().upper()
        resolution_rate = _safe_float(policy.get("resolution_rate"), 0.0)

        if risk_level == "HIGH" and route_policy == "LIGHT":
            failures.append(f"high-risk intent downgraded to LIGHT route: {intent}")
        if resolution_rate < max(0.0, float(min_resolution_rate)) and route_policy == "LIGHT":
            failures.append(
                f"low-resolution intent routed to LIGHT: {intent} ({resolution_rate:.4f} < {float(min_resolution_rate):.4f})"
            )
        if risk_level == "LOW" and route_policy == "LIGHT":
            low_risk_light_total += 1

    if mode == "HARD_CLAMP" and low_risk_light_total == 0:
        failures.append("hard clamp mode selected but no low-risk intent moved to LIGHT route")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Cost Optimizer Policy")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- budget_utilization: {_safe_float(decision.get('budget_utilization'), 0.0):.4f}")
    lines.append(f"- mode: {decision.get('mode')}")
    lines.append(f"- estimated_savings_total_usd: {_safe_float(decision.get('estimated_savings_total_usd'), 0.0):.4f}")
    lines.append("")
    lines.append("## Intent Policies")
    lines.append("")
    for row in decision.get("intent_policies") if isinstance(decision.get("intent_policies"), list) else []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            "- "
            f"{str(row.get('intent') or 'UNKNOWN').upper()}: "
            f"risk={row.get('risk_level')} route={row.get('route_policy')} action={row.get('action')} "
            f"resolution_rate={_safe_float(row.get('resolution_rate'), 0.0):.4f} "
            f"cost_per_resolved_session={_safe_float(row.get('cost_per_resolved_session'), 0.0):.4f}"
        )

    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    else:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cost optimizer policy decisions under quality/budget constraints.")
    parser.add_argument("--events-jsonl", default="var/chat_finops/session_cost_events.jsonl")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--budget-utilization", type=float, default=-1.0)
    parser.add_argument("--soft-budget-utilization", type=float, default=0.75)
    parser.add_argument("--hard-budget-utilization", type=float, default=0.90)
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-resolution-rate", type=float, default=0.80)
    parser.add_argument("--max-cost-per-resolved-session", type=float, default=2.5)
    parser.add_argument(
        "--high-risk-intents",
        default="CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE",
    )
    parser.add_argument("--require-clamp", action="store_true")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_cost_optimizer_policy")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_days=max(1, int(args.window_days)),
        limit=max(1, int(args.limit)),
    )

    summary = summarize_cost_events(events)
    budget_utilization = infer_budget_utilization(
        events,
        override=None if float(args.budget_utilization) < 0 else float(args.budget_utilization),
    )
    high_risk_intents = {
        token.strip().upper()
        for token in str(args.high_risk_intents).split(",")
        if token.strip()
    }
    decision = decide_optimizer_policy(
        summary,
        budget_utilization=budget_utilization,
        soft_budget_utilization=max(0.0, float(args.soft_budget_utilization)),
        hard_budget_utilization=max(0.0, float(args.hard_budget_utilization)),
        min_resolution_rate=max(0.0, float(args.min_resolution_rate)),
        max_cost_per_resolved_session=max(0.0, float(args.max_cost_per_resolved_session)),
        high_risk_intents=high_risk_intents,
    )
    failures = evaluate_gate(
        summary,
        decision,
        min_window=max(0, int(args.min_window)),
        min_resolution_rate=max(0.0, float(args.min_resolution_rate)),
        soft_budget_utilization=max(0.0, float(args.soft_budget_utilization)),
        hard_budget_utilization=max(0.0, float(args.hard_budget_utilization)),
        require_clamp=bool(args.require_clamp),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "summary": summary,
        "decision": decision,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_resolution_rate": float(args.min_resolution_rate),
                "max_cost_per_resolved_session": float(args.max_cost_per_resolved_session),
                "soft_budget_utilization": float(args.soft_budget_utilization),
                "hard_budget_utilization": float(args.hard_budget_utilization),
                "require_clamp": bool(args.require_clamp),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"mode={decision.get('mode')}")
    print(f"budget_utilization={_safe_float(decision.get('budget_utilization'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
