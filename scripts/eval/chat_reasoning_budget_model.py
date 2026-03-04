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
TOKEN_KEYS = ("token_budget", "max_tokens", "max_total_tokens", "max_prompt_tokens")
STEP_KEYS = ("step_budget", "max_steps", "reasoning_steps")
TOOL_KEYS = ("tool_call_budget", "max_tool_calls", "tool_budget")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, Mapping):
        return {str(k): v for k, v in payload.items()}
    return {}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _first_int(row: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        parsed = _safe_int(value, -1)
        if parsed >= 0:
            return parsed
    return None


def _scope_key(row: Mapping[str, Any]) -> str:
    tenant = str(row.get("tenant_id") or row.get("tenant") or "*").strip() or "*"
    user_tier = str(row.get("user_tier") or row.get("segment") or "*").strip() or "*"
    intent = str(row.get("intent") or row.get("intent_type") or "*").strip().upper() or "*"
    return f"{tenant}|{user_tier}|{intent}"


def _policy_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    defaults = payload.get("defaults")
    if isinstance(defaults, Mapping):
        item = {str(k): v for k, v in defaults.items()}
        item.setdefault("tenant_id", "*")
        item.setdefault("intent", "*")
        item.setdefault("user_tier", "*")
        items.append(item)

    for key in ("policies", "rules", "overrides", "intent_policies"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                items.append({str(k): v for k, v in row.items()})
    return items


def summarize_budget_model(
    payload: Mapping[str, Any],
    *,
    required_sensitive_intents: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    version = str(payload.get("version") or payload.get("policy_version") or "").strip()
    updated_at = _parse_ts(payload.get("updated_at") or payload.get("generated_at") or payload.get("timestamp"))
    stale_minutes = 999999.0 if updated_at is None else max(0.0, (now_dt - updated_at).total_seconds() / 60.0)

    items = _policy_items(payload)
    policy_total = len(items)
    missing_budget_field_total = 0
    invalid_limit_total = 0
    duplicate_scope_total = 0
    seen_scopes: set[str] = set()
    covered_sensitive_intents: set[str] = set()

    for item in items:
        scope = _scope_key(item)
        if scope in seen_scopes:
            duplicate_scope_total += 1
        else:
            seen_scopes.add(scope)

        token_budget = _first_int(item, TOKEN_KEYS)
        step_budget = _first_int(item, STEP_KEYS)
        tool_budget = _first_int(item, TOOL_KEYS)
        if token_budget is None or step_budget is None or tool_budget is None:
            missing_budget_field_total += 1

        for value in (token_budget, step_budget, tool_budget):
            if value is None:
                continue
            if value <= 0:
                invalid_limit_total += 1

        soft_token = _safe_int(item.get("soft_token_budget"), -1)
        hard_token = _safe_int(item.get("hard_token_budget"), -1)
        if soft_token > 0 and hard_token > 0 and soft_token > hard_token:
            invalid_limit_total += 1

        intent = str(item.get("intent") or item.get("intent_type") or "").strip().upper()
        if intent in required_sensitive_intents and token_budget and step_budget and tool_budget:
            covered_sensitive_intents.add(intent)

    missing_sensitive_intents = sorted(required_sensitive_intents - covered_sensitive_intents)
    override_total = max(0, policy_total - (1 if isinstance(payload.get("defaults"), Mapping) else 0))

    return {
        "policy_version": version,
        "version_missing": len(version) == 0,
        "policy_total": policy_total,
        "override_total": override_total,
        "missing_budget_field_total": missing_budget_field_total,
        "invalid_limit_total": invalid_limit_total,
        "duplicate_scope_total": duplicate_scope_total,
        "covered_sensitive_intent_total": len(covered_sensitive_intents),
        "missing_sensitive_intents": missing_sensitive_intents,
        "missing_sensitive_intent_total": len(missing_sensitive_intents),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_policy_total: int,
    require_policy_version: bool,
    max_missing_budget_field_total: int,
    max_invalid_limit_total: int,
    max_duplicate_scope_total: int,
    max_missing_sensitive_intent_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    policy_total = _safe_int(summary.get("policy_total"), 0)
    version_missing = _safe_bool(summary.get("version_missing"), True)
    missing_budget_field_total = _safe_int(summary.get("missing_budget_field_total"), 0)
    invalid_limit_total = _safe_int(summary.get("invalid_limit_total"), 0)
    duplicate_scope_total = _safe_int(summary.get("duplicate_scope_total"), 0)
    missing_sensitive_intent_total = _safe_int(summary.get("missing_sensitive_intent_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if policy_total < max(0, int(min_policy_total)):
        failures.append(f"reasoning budget policy total too small: {policy_total} < {int(min_policy_total)}")
    if require_policy_version and version_missing:
        failures.append("reasoning budget policy version is required")
    if missing_budget_field_total > max(0, int(max_missing_budget_field_total)):
        failures.append(
            "reasoning budget missing field total exceeded: "
            f"{missing_budget_field_total} > {int(max_missing_budget_field_total)}"
        )
    if invalid_limit_total > max(0, int(max_invalid_limit_total)):
        failures.append(f"reasoning budget invalid limit total exceeded: {invalid_limit_total} > {int(max_invalid_limit_total)}")
    if duplicate_scope_total > max(0, int(max_duplicate_scope_total)):
        failures.append(
            f"reasoning budget duplicate scope total exceeded: {duplicate_scope_total} > {int(max_duplicate_scope_total)}"
        )
    if missing_sensitive_intent_total > max(0, int(max_missing_sensitive_intent_total)):
        failures.append(
            "reasoning budget missing sensitive intent total exceeded: "
            f"{missing_sensitive_intent_total} > {int(max_missing_sensitive_intent_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"reasoning budget policy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_policy_total_drop: int,
    max_version_missing_total_increase: int,
    max_missing_budget_field_total_increase: int,
    max_invalid_limit_total_increase: int,
    max_duplicate_scope_total_increase: int,
    max_missing_sensitive_intent_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_policy_total = _safe_int(base_summary.get("policy_total"), 0)
    cur_policy_total = _safe_int(current_summary.get("policy_total"), 0)
    policy_total_drop = max(0, base_policy_total - cur_policy_total)
    if policy_total_drop > max(0, int(max_policy_total_drop)):
        failures.append(
            f"policy_total regression: baseline={base_policy_total}, current={cur_policy_total}, "
            f"allowed_drop={max(0, int(max_policy_total_drop))}"
        )

    base_version_missing_total = 1 if _safe_bool(base_summary.get("version_missing"), False) else 0
    cur_version_missing_total = 1 if _safe_bool(current_summary.get("version_missing"), False) else 0
    version_missing_total_increase = max(0, cur_version_missing_total - base_version_missing_total)
    if version_missing_total_increase > max(0, int(max_version_missing_total_increase)):
        failures.append(
            "version_missing regression: "
            f"baseline={base_version_missing_total}, current={cur_version_missing_total}, "
            f"allowed_increase={max(0, int(max_version_missing_total_increase))}"
        )

    baseline_pairs = [
        ("missing_budget_field_total", max_missing_budget_field_total_increase),
        ("invalid_limit_total", max_invalid_limit_total_increase),
        ("duplicate_scope_total", max_duplicate_scope_total_increase),
        ("missing_sensitive_intent_total", max_missing_sensitive_intent_total_increase),
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
    lines.append("# Chat Reasoning Budget Model")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- policy_json: {payload.get('policy_json')}")
    lines.append(f"- policy_total: {_safe_int(summary.get('policy_total'), 0)}")
    lines.append(f"- missing_budget_field_total: {_safe_int(summary.get('missing_budget_field_total'), 0)}")
    lines.append(f"- invalid_limit_total: {_safe_int(summary.get('invalid_limit_total'), 0)}")
    lines.append(f"- duplicate_scope_total: {_safe_int(summary.get('duplicate_scope_total'), 0)}")
    lines.append(f"- missing_sensitive_intent_total: {_safe_int(summary.get('missing_sensitive_intent_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Lint and gate reasoning budget policy model.")
    parser.add_argument("--policy-json", default="var/chat_budget/budget_policy.json")
    parser.add_argument(
        "--required-sensitive-intents",
        default="CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE",
    )
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_reasoning_budget_model")
    parser.add_argument("--min-policy-total", type=int, default=0)
    parser.add_argument("--require-policy-version", action="store_true")
    parser.add_argument("--max-missing-budget-field-total", type=int, default=0)
    parser.add_argument("--max-invalid-limit-total", type=int, default=0)
    parser.add_argument("--max-duplicate-scope-total", type=int, default=0)
    parser.add_argument("--max-missing-sensitive-intent-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-policy-total-drop", type=int, default=5)
    parser.add_argument("--max-version-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-budget-field-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-limit-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-scope-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-sensitive-intent-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    policy_path = Path(args.policy_json)
    payload = _read_json(policy_path)
    required_sensitive_intents = {
        token.strip().upper()
        for token in str(args.required_sensitive_intents).split(",")
        if token.strip()
    } or set(SENSITIVE_INTENTS_DEFAULT)
    summary = summarize_budget_model(payload, required_sensitive_intents=required_sensitive_intents)
    failures = evaluate_gate(
        summary,
        min_policy_total=max(0, int(args.min_policy_total)),
        require_policy_version=bool(args.require_policy_version),
        max_missing_budget_field_total=max(0, int(args.max_missing_budget_field_total)),
        max_invalid_limit_total=max(0, int(args.max_invalid_limit_total)),
        max_duplicate_scope_total=max(0, int(args.max_duplicate_scope_total)),
        max_missing_sensitive_intent_total=max(0, int(args.max_missing_sensitive_intent_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_policy_total_drop=max(0, int(args.max_policy_total_drop)),
            max_version_missing_total_increase=max(0, int(args.max_version_missing_total_increase)),
            max_missing_budget_field_total_increase=max(0, int(args.max_missing_budget_field_total_increase)),
            max_invalid_limit_total_increase=max(0, int(args.max_invalid_limit_total_increase)),
            max_duplicate_scope_total_increase=max(0, int(args.max_duplicate_scope_total_increase)),
            max_missing_sensitive_intent_total_increase=max(
                0, int(args.max_missing_sensitive_intent_total_increase)
            ),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_json": str(policy_path),
        "source": {
            "policy_json": str(policy_path),
            "required_sensitive_intents": sorted(required_sensitive_intents),
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
                "min_policy_total": int(args.min_policy_total),
                "require_policy_version": bool(args.require_policy_version),
                "max_missing_budget_field_total": int(args.max_missing_budget_field_total),
                "max_invalid_limit_total": int(args.max_invalid_limit_total),
                "max_duplicate_scope_total": int(args.max_duplicate_scope_total),
                "max_missing_sensitive_intent_total": int(args.max_missing_sensitive_intent_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_policy_total_drop": int(args.max_policy_total_drop),
                "max_version_missing_total_increase": int(args.max_version_missing_total_increase),
                "max_missing_budget_field_total_increase": int(args.max_missing_budget_field_total_increase),
                "max_invalid_limit_total_increase": int(args.max_invalid_limit_total_increase),
                "max_duplicate_scope_total_increase": int(args.max_duplicate_scope_total_increase),
                "max_missing_sensitive_intent_total_increase": int(
                    args.max_missing_sensitive_intent_total_increase
                ),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"policy_total={_safe_int(summary.get('policy_total'), 0)}")
    print(f"missing_budget_field_total={_safe_int(summary.get('missing_budget_field_total'), 0)}")
    print(f"invalid_limit_total={_safe_int(summary.get('invalid_limit_total'), 0)}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
