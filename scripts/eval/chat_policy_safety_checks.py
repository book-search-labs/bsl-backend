#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SENSITIVE_INTENTS_DEFAULT = {
    "CANCEL_ORDER",
    "REFUND_REQUEST",
    "ADDRESS_CHANGE",
    "PAYMENT_CHANGE",
}
GUARD_ACTIONS_DEFAULT = {"DENY", "REQUIRE_CONFIRMATION", "HANDOFF"}
ACTION_ALIASES = {
    "BLOCK": "DENY",
    "ESCALATE": "HANDOFF",
    "HUMAN_HANDOFF": "HANDOFF",
    "CONFIRM": "REQUIRE_CONFIRMATION",
    "CLARIFY": "ASK_CLARIFICATION",
}


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


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            return {}
        if isinstance(payload, Mapping):
            return {str(k): v for k, v in payload.items()}
    return {}


def _as_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return "UNKNOWN"
    return ACTION_ALIASES.get(text, text)


def _load_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, Mapping):
        return {str(k): v for k, v in payload.items()}
    if isinstance(payload, list):
        return {"rules": payload}
    return {}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _extract_rules(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("rules", "policy_rules", "chat_policy_rule"):
        raw = bundle.get(key)
        if isinstance(raw, list):
            rows: list[dict[str, Any]] = []
            for item in raw:
                if isinstance(item, Mapping):
                    rows.append({str(k): v for k, v in item.items()})
            return rows
    return []


def _extract_condition(rule: Mapping[str, Any]) -> dict[str, Any]:
    condition = _as_mapping(rule.get("condition") or rule.get("condition_json") or rule.get("when"))
    if condition:
        return condition
    fallback: dict[str, Any] = {}
    for key in ("intent", "risk_level", "reliability_level", "locale", "user_tier"):
        if key in rule:
            fallback[key] = rule.get(key)
    return fallback


def _extract_action(rule: Mapping[str, Any]) -> dict[str, Any]:
    action = _as_mapping(rule.get("action") or rule.get("action_json") or rule.get("then"))
    if action:
        return action
    fallback = rule.get("decision") or rule.get("action_type") or rule.get("action")
    if fallback is not None:
        return {"type": fallback}
    return {}


def _condition_signature(condition: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted(condition.keys()):
        values = [item.upper() for item in _as_values(condition.get(key))]
        parts.append(f"{key.lower()}={','.join(sorted(values))}")
    return "|".join(parts)


def summarize_policy_safety(
    bundle: Mapping[str, Any],
    *,
    sensitive_intents: set[str],
    guard_actions: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    rules = _extract_rules(bundle)
    latest_ts: datetime | None = None
    for source in [bundle, *rules]:
        for key in ("updated_at", "created_at", "generated_at", "timestamp"):
            ts = _parse_ts(source.get(key))
            if ts is not None and (latest_ts is None or ts > latest_ts):
                latest_ts = ts

    group_actions: dict[tuple[int, str], set[str]] = {}
    group_rule_count: dict[tuple[int, str, str], int] = {}

    unsafe_high_risk_allow_total = 0
    missing_reason_code_total = 0
    sensitive_guard_hit: dict[str, bool] = {intent: False for intent in sensitive_intents}

    for rule in rules:
        if not _safe_bool(rule.get("enabled"), True):
            continue
        priority = _safe_int(rule.get("priority"), 0)
        condition = _extract_condition(rule)
        action_obj = _extract_action(rule)
        action = _normalize_action(
            action_obj.get("type") or action_obj.get("action") or action_obj.get("decision") or rule.get("action")
        )
        signature = _condition_signature(condition)

        group_actions.setdefault((priority, signature), set()).add(action)
        group_rule_count[(priority, signature, action)] = group_rule_count.get((priority, signature, action), 0) + 1

        reason_code = str(action_obj.get("reason_code") or rule.get("reason_code") or "").strip()
        if not reason_code:
            missing_reason_code_total += 1

        intents = {item.upper() for item in _as_values(condition.get("intent"))}
        risk_levels = {item.upper() for item in _as_values(condition.get("risk_level"))}

        if action == "ALLOW":
            if "HIGH" in risk_levels or "WRITE_SENSITIVE" in risk_levels:
                unsafe_high_risk_allow_total += 1
            if intents.intersection(sensitive_intents):
                unsafe_high_risk_allow_total += 1

        if action in guard_actions:
            for intent in intents.intersection(sensitive_intents):
                sensitive_guard_hit[intent] = True

    contradictory_rule_pair_total = sum(1 for actions in group_actions.values() if len(actions) > 1)
    duplicate_condition_total = sum(1 for count in group_rule_count.values() if count > 1)
    missing_sensitive_guard_intent_total = sum(1 for matched in sensitive_guard_hit.values() if not matched)

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "policy_version": str(bundle.get("policy_version") or bundle.get("version") or "").strip(),
        "rule_total": len(rules),
        "contradictory_rule_pair_total": contradictory_rule_pair_total,
        "duplicate_condition_total": duplicate_condition_total,
        "missing_sensitive_guard_intent_total": missing_sensitive_guard_intent_total,
        "unsafe_high_risk_allow_total": unsafe_high_risk_allow_total,
        "missing_reason_code_total": missing_reason_code_total,
        "latest_bundle_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_rule_total: int,
    max_contradictory_rule_pair_total: int,
    max_duplicate_condition_total: int,
    max_missing_sensitive_guard_intent_total: int,
    max_unsafe_high_risk_allow_total: int,
    max_missing_reason_code_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    rule_total = _safe_int(summary.get("rule_total"), 0)
    contradictory_rule_pair_total = _safe_int(summary.get("contradictory_rule_pair_total"), 0)
    duplicate_condition_total = _safe_int(summary.get("duplicate_condition_total"), 0)
    missing_sensitive_guard_intent_total = _safe_int(summary.get("missing_sensitive_guard_intent_total"), 0)
    unsafe_high_risk_allow_total = _safe_int(summary.get("unsafe_high_risk_allow_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if rule_total < max(0, int(min_rule_total)):
        failures.append(f"policy safety rule total too small: {rule_total} < {int(min_rule_total)}")
    if rule_total == 0:
        return failures

    if contradictory_rule_pair_total > max(0, int(max_contradictory_rule_pair_total)):
        failures.append(
            "policy safety contradictory rule pair total exceeded: "
            f"{contradictory_rule_pair_total} > {int(max_contradictory_rule_pair_total)}"
        )
    if duplicate_condition_total > max(0, int(max_duplicate_condition_total)):
        failures.append(f"policy safety duplicate condition total exceeded: {duplicate_condition_total} > {int(max_duplicate_condition_total)}")
    if missing_sensitive_guard_intent_total > max(0, int(max_missing_sensitive_guard_intent_total)):
        failures.append(
            "policy safety missing sensitive guard intent total exceeded: "
            f"{missing_sensitive_guard_intent_total} > {int(max_missing_sensitive_guard_intent_total)}"
        )
    if unsafe_high_risk_allow_total > max(0, int(max_unsafe_high_risk_allow_total)):
        failures.append(
            f"policy safety unsafe high-risk allow total exceeded: {unsafe_high_risk_allow_total} > {int(max_unsafe_high_risk_allow_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(f"policy safety missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"policy safety bundle stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_contradictory_rule_pair_total_increase: int,
    max_duplicate_condition_total_increase: int,
    max_missing_sensitive_guard_intent_total_increase: int,
    max_unsafe_high_risk_allow_total_increase: int,
    max_missing_reason_code_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_pairs = [
        ("contradictory_rule_pair_total", max_contradictory_rule_pair_total_increase),
        ("duplicate_condition_total", max_duplicate_condition_total_increase),
        ("missing_sensitive_guard_intent_total", max_missing_sensitive_guard_intent_total_increase),
        ("unsafe_high_risk_allow_total", max_unsafe_high_risk_allow_total_increase),
        ("missing_reason_code_total", max_missing_reason_code_total_increase),
    ]
    for key, allowed_increase in baseline_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Policy Safety Checks")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- bundle_json: {payload.get('bundle_json')}")
    lines.append(f"- rule_total: {_safe_int(summary.get('rule_total'), 0)}")
    lines.append(f"- contradictory_rule_pair_total: {_safe_int(summary.get('contradictory_rule_pair_total'), 0)}")
    lines.append(f"- missing_sensitive_guard_intent_total: {_safe_int(summary.get('missing_sensitive_guard_intent_total'), 0)}")
    lines.append(f"- unsafe_high_risk_allow_total: {_safe_int(summary.get('unsafe_high_risk_allow_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate policy safety checks for contradictions and missing guards.")
    parser.add_argument("--bundle-json", default="var/chat_policy/policy_bundle.json")
    parser.add_argument("--sensitive-intents", default="CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE")
    parser.add_argument("--guard-actions", default="DENY,REQUIRE_CONFIRMATION,HANDOFF")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_policy_safety_checks")
    parser.add_argument("--min-rule-total", type=int, default=0)
    parser.add_argument("--max-contradictory-rule-pair-total", type=int, default=0)
    parser.add_argument("--max-duplicate-condition-total", type=int, default=0)
    parser.add_argument("--max-missing-sensitive-guard-intent-total", type=int, default=0)
    parser.add_argument("--max-unsafe-high-risk-allow-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-contradictory-rule-pair-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-condition-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-sensitive-guard-intent-total-increase", type=int, default=0)
    parser.add_argument("--max-unsafe-high-risk-allow-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bundle_path = Path(args.bundle_json)
    bundle = _load_bundle(bundle_path)
    sensitive_intents = {
        item.strip().upper() for item in str(args.sensitive_intents).split(",") if item.strip()
    } or set(SENSITIVE_INTENTS_DEFAULT)
    guard_actions = {
        item.strip().upper() for item in str(args.guard_actions).split(",") if item.strip()
    } or set(GUARD_ACTIONS_DEFAULT)

    summary = summarize_policy_safety(bundle, sensitive_intents=sensitive_intents, guard_actions=guard_actions)
    failures = evaluate_gate(
        summary,
        min_rule_total=max(0, int(args.min_rule_total)),
        max_contradictory_rule_pair_total=max(0, int(args.max_contradictory_rule_pair_total)),
        max_duplicate_condition_total=max(0, int(args.max_duplicate_condition_total)),
        max_missing_sensitive_guard_intent_total=max(0, int(args.max_missing_sensitive_guard_intent_total)),
        max_unsafe_high_risk_allow_total=max(0, int(args.max_unsafe_high_risk_allow_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_contradictory_rule_pair_total_increase=max(0, int(args.max_contradictory_rule_pair_total_increase)),
            max_duplicate_condition_total_increase=max(0, int(args.max_duplicate_condition_total_increase)),
            max_missing_sensitive_guard_intent_total_increase=max(
                0, int(args.max_missing_sensitive_guard_intent_total_increase)
            ),
            max_unsafe_high_risk_allow_total_increase=max(0, int(args.max_unsafe_high_risk_allow_total_increase)),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_json": str(bundle_path),
        "source": {
            "bundle_json": str(bundle_path),
            "sensitive_intents": sorted(sensitive_intents),
            "guard_actions": sorted(guard_actions),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_rule_total": int(args.min_rule_total),
                "max_contradictory_rule_pair_total": int(args.max_contradictory_rule_pair_total),
                "max_duplicate_condition_total": int(args.max_duplicate_condition_total),
                "max_missing_sensitive_guard_intent_total": int(args.max_missing_sensitive_guard_intent_total),
                "max_unsafe_high_risk_allow_total": int(args.max_unsafe_high_risk_allow_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_contradictory_rule_pair_total_increase": int(args.max_contradictory_rule_pair_total_increase),
                "max_duplicate_condition_total_increase": int(args.max_duplicate_condition_total_increase),
                "max_missing_sensitive_guard_intent_total_increase": int(
                    args.max_missing_sensitive_guard_intent_total_increase
                ),
                "max_unsafe_high_risk_allow_total_increase": int(args.max_unsafe_high_risk_allow_total_increase),
                "max_missing_reason_code_total_increase": int(args.max_missing_reason_code_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"rule_total={_safe_int(summary.get('rule_total'), 0)}")
    print(f"unsafe_high_risk_allow_total={_safe_int(summary.get('unsafe_high_risk_allow_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
