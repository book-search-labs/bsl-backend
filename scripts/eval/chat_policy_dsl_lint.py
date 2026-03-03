#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ALLOWED_ACTIONS = {
    "ALLOW",
    "DENY",
    "ASK_CLARIFICATION",
    "REQUIRE_CONFIRMATION",
    "HANDOFF",
}
ACTION_ALIASES = {
    "ASK": "ASK_CLARIFICATION",
    "CLARIFY": "ASK_CLARIFICATION",
    "CONFIRM": "REQUIRE_CONFIRMATION",
    "ESCALATE": "HANDOFF",
    "HUMAN_HANDOFF": "HANDOFF",
    "BLOCK": "DENY",
}
ALLOWED_CONDITION_KEYS = {"intent", "user_tier", "risk_level", "reliability_level", "locale"}
ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "WRITE_SENSITIVE"}
ALLOWED_RELIABILITY_LEVELS = {"LOW", "MEDIUM", "HIGH"}
LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


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


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return "UNKNOWN"
    return ACTION_ALIASES.get(text, text)


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
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _load_json_payload(path: Path) -> dict[str, Any]:
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

    rules: list[dict[str, Any]] = []
    for line in text.splitlines():
        row_text = line.strip()
        if not row_text:
            continue
        try:
            row_payload = json.loads(row_text)
        except Exception:
            continue
        if isinstance(row_payload, Mapping):
            rules.append({str(k): v for k, v in row_payload.items()})
    return {"rules": rules}


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
    for key in ALLOWED_CONDITION_KEYS:
        if key in rule:
            fallback[key] = rule.get(key)
    return fallback


def _extract_action(rule: Mapping[str, Any]) -> dict[str, Any]:
    action = _as_mapping(rule.get("action") or rule.get("action_json") or rule.get("then"))
    if action:
        return action
    decision = rule.get("decision") or rule.get("action_type") or rule.get("result")
    if decision is not None:
        return {"type": decision}
    return {}


def _latest_ts(bundle: Mapping[str, Any], rules: list[Mapping[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for source in [bundle, *rules]:
        for key in ("updated_at", "created_at", "generated_at", "timestamp"):
            ts = _parse_ts(source.get(key))
            if ts is not None and (latest is None or ts > latest):
                latest = ts
    return latest


def summarize_policy_dsl(bundle: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    rules = _extract_rules(bundle)
    policy_version = str(bundle.get("policy_version") or bundle.get("version") or bundle.get("bundle_version") or "").strip()

    enabled_rule_total = 0
    missing_rule_id_total = 0
    duplicate_rule_id_total = 0
    invalid_priority_total = 0
    invalid_action_total = 0
    empty_condition_total = 0
    unknown_condition_key_total = 0
    invalid_risk_level_total = 0
    invalid_reliability_level_total = 0
    invalid_locale_total = 0
    invalid_effective_window_total = 0
    action_distribution: dict[str, int] = {}

    seen_rule_ids: set[str] = set()
    duplicate_rule_ids: set[str] = set()

    for rule in rules:
        if _safe_bool(rule.get("enabled"), True):
            enabled_rule_total += 1

        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        if not rule_id:
            missing_rule_id_total += 1
        elif rule_id in seen_rule_ids:
            duplicate_rule_ids.add(rule_id)
        else:
            seen_rule_ids.add(rule_id)

        priority = rule.get("priority")
        if priority is None:
            invalid_priority_total += 1
        else:
            try:
                int(priority)
            except Exception:
                invalid_priority_total += 1

        action = _extract_action(rule)
        action_type = _normalize_action(
            action.get("type") or action.get("action") or action.get("decision") or rule.get("action")
        )
        action_distribution[action_type] = action_distribution.get(action_type, 0) + 1
        if action_type not in ALLOWED_ACTIONS:
            invalid_action_total += 1

        condition = _extract_condition(rule)
        if not condition:
            empty_condition_total += 1
        else:
            for key, value in condition.items():
                key_norm = str(key).strip().lower()
                if key_norm not in ALLOWED_CONDITION_KEYS:
                    unknown_condition_key_total += 1
                    continue
                values = _as_values(value)
                if key_norm == "risk_level":
                    for item in values:
                        if item.upper() not in ALLOWED_RISK_LEVELS:
                            invalid_risk_level_total += 1
                elif key_norm == "reliability_level":
                    for item in values:
                        if item.upper() not in ALLOWED_RELIABILITY_LEVELS:
                            invalid_reliability_level_total += 1
                elif key_norm == "locale":
                    for item in values:
                        if item == "*":
                            continue
                        if not LOCALE_RE.match(item):
                            invalid_locale_total += 1

        start_ts = _parse_ts(rule.get("effective_from") or rule.get("starts_at") or rule.get("valid_from"))
        end_ts = _parse_ts(rule.get("effective_to") or rule.get("expires_at") or rule.get("valid_to"))
        if start_ts is not None and end_ts is not None and start_ts > end_ts:
            invalid_effective_window_total += 1

    duplicate_rule_id_total = len(duplicate_rule_ids)
    latest_ts = _latest_ts(bundle, rules)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "policy_version": policy_version,
        "rule_total": len(rules),
        "enabled_rule_total": enabled_rule_total,
        "missing_rule_id_total": missing_rule_id_total,
        "duplicate_rule_id_total": duplicate_rule_id_total,
        "invalid_priority_total": invalid_priority_total,
        "invalid_action_total": invalid_action_total,
        "empty_condition_total": empty_condition_total,
        "unknown_condition_key_total": unknown_condition_key_total,
        "invalid_risk_level_total": invalid_risk_level_total,
        "invalid_reliability_level_total": invalid_reliability_level_total,
        "invalid_locale_total": invalid_locale_total,
        "invalid_effective_window_total": invalid_effective_window_total,
        "action_distribution": [
            {"action": key, "count": value}
            for key, value in sorted(action_distribution.items(), key=lambda item: item[0])
        ],
        "latest_bundle_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_rule_total: int,
    require_policy_version: bool,
    max_missing_rule_id_total: int,
    max_duplicate_rule_id_total: int,
    max_invalid_priority_total: int,
    max_invalid_action_total: int,
    max_empty_condition_total: int,
    max_unknown_condition_key_total: int,
    max_invalid_risk_level_total: int,
    max_invalid_reliability_level_total: int,
    max_invalid_locale_total: int,
    max_invalid_effective_window_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    rule_total = _safe_int(summary.get("rule_total"), 0)
    policy_version = str(summary.get("policy_version") or "").strip()
    missing_rule_id_total = _safe_int(summary.get("missing_rule_id_total"), 0)
    duplicate_rule_id_total = _safe_int(summary.get("duplicate_rule_id_total"), 0)
    invalid_priority_total = _safe_int(summary.get("invalid_priority_total"), 0)
    invalid_action_total = _safe_int(summary.get("invalid_action_total"), 0)
    empty_condition_total = _safe_int(summary.get("empty_condition_total"), 0)
    unknown_condition_key_total = _safe_int(summary.get("unknown_condition_key_total"), 0)
    invalid_risk_level_total = _safe_int(summary.get("invalid_risk_level_total"), 0)
    invalid_reliability_level_total = _safe_int(summary.get("invalid_reliability_level_total"), 0)
    invalid_locale_total = _safe_int(summary.get("invalid_locale_total"), 0)
    invalid_effective_window_total = _safe_int(summary.get("invalid_effective_window_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if require_policy_version and not policy_version:
        failures.append("policy_version missing")
    if rule_total < max(0, int(min_rule_total)):
        failures.append(f"policy rule total too small: {rule_total} < {int(min_rule_total)}")
    if rule_total == 0:
        return failures

    if missing_rule_id_total > max(0, int(max_missing_rule_id_total)):
        failures.append(f"missing rule_id total exceeded: {missing_rule_id_total} > {int(max_missing_rule_id_total)}")
    if duplicate_rule_id_total > max(0, int(max_duplicate_rule_id_total)):
        failures.append(f"duplicate rule_id total exceeded: {duplicate_rule_id_total} > {int(max_duplicate_rule_id_total)}")
    if invalid_priority_total > max(0, int(max_invalid_priority_total)):
        failures.append(f"invalid priority total exceeded: {invalid_priority_total} > {int(max_invalid_priority_total)}")
    if invalid_action_total > max(0, int(max_invalid_action_total)):
        failures.append(f"invalid action total exceeded: {invalid_action_total} > {int(max_invalid_action_total)}")
    if empty_condition_total > max(0, int(max_empty_condition_total)):
        failures.append(f"empty condition total exceeded: {empty_condition_total} > {int(max_empty_condition_total)}")
    if unknown_condition_key_total > max(0, int(max_unknown_condition_key_total)):
        failures.append(
            f"unknown condition key total exceeded: {unknown_condition_key_total} > {int(max_unknown_condition_key_total)}"
        )
    if invalid_risk_level_total > max(0, int(max_invalid_risk_level_total)):
        failures.append(
            f"invalid risk_level total exceeded: {invalid_risk_level_total} > {int(max_invalid_risk_level_total)}"
        )
    if invalid_reliability_level_total > max(0, int(max_invalid_reliability_level_total)):
        failures.append(
            "invalid reliability_level total exceeded: "
            f"{invalid_reliability_level_total} > {int(max_invalid_reliability_level_total)}"
        )
    if invalid_locale_total > max(0, int(max_invalid_locale_total)):
        failures.append(f"invalid locale total exceeded: {invalid_locale_total} > {int(max_invalid_locale_total)}")
    if invalid_effective_window_total > max(0, int(max_invalid_effective_window_total)):
        failures.append(
            "invalid effective window total exceeded: "
            f"{invalid_effective_window_total} > {int(max_invalid_effective_window_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"policy bundle stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_missing_rule_id_total_increase: int,
    max_duplicate_rule_id_total_increase: int,
    max_invalid_priority_total_increase: int,
    max_invalid_action_total_increase: int,
    max_empty_condition_total_increase: int,
    max_unknown_condition_key_total_increase: int,
    max_invalid_risk_level_total_increase: int,
    max_invalid_reliability_level_total_increase: int,
    max_invalid_locale_total_increase: int,
    max_invalid_effective_window_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_pairs = [
        ("missing_rule_id_total", max_missing_rule_id_total_increase),
        ("duplicate_rule_id_total", max_duplicate_rule_id_total_increase),
        ("invalid_priority_total", max_invalid_priority_total_increase),
        ("invalid_action_total", max_invalid_action_total_increase),
        ("empty_condition_total", max_empty_condition_total_increase),
        ("unknown_condition_key_total", max_unknown_condition_key_total_increase),
        ("invalid_risk_level_total", max_invalid_risk_level_total_increase),
        ("invalid_reliability_level_total", max_invalid_reliability_level_total_increase),
        ("invalid_locale_total", max_invalid_locale_total_increase),
        ("invalid_effective_window_total", max_invalid_effective_window_total_increase),
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
    lines.append("# Chat Policy DSL Lint")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- bundle_json: {payload.get('bundle_json')}")
    lines.append(f"- policy_version: {summary.get('policy_version') or '(missing)'}")
    lines.append(f"- rule_total: {_safe_int(summary.get('rule_total'), 0)}")
    lines.append(f"- invalid_action_total: {_safe_int(summary.get('invalid_action_total'), 0)}")
    lines.append(f"- unknown_condition_key_total: {_safe_int(summary.get('unknown_condition_key_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat policy DSL lint and schema conformance.")
    parser.add_argument("--bundle-json", default="var/chat_policy/policy_bundle.json")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_policy_dsl_lint")
    parser.add_argument("--min-rule-total", type=int, default=0)
    parser.add_argument("--require-policy-version", type=int, default=0)
    parser.add_argument("--max-missing-rule-id-total", type=int, default=0)
    parser.add_argument("--max-duplicate-rule-id-total", type=int, default=0)
    parser.add_argument("--max-invalid-priority-total", type=int, default=0)
    parser.add_argument("--max-invalid-action-total", type=int, default=0)
    parser.add_argument("--max-empty-condition-total", type=int, default=0)
    parser.add_argument("--max-unknown-condition-key-total", type=int, default=0)
    parser.add_argument("--max-invalid-risk-level-total", type=int, default=0)
    parser.add_argument("--max-invalid-reliability-level-total", type=int, default=0)
    parser.add_argument("--max-invalid-locale-total", type=int, default=0)
    parser.add_argument("--max-invalid-effective-window-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-missing-rule-id-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-rule-id-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-priority-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-action-total-increase", type=int, default=0)
    parser.add_argument("--max-empty-condition-total-increase", type=int, default=0)
    parser.add_argument("--max-unknown-condition-key-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-risk-level-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-reliability-level-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-locale-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-effective-window-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bundle_path = Path(args.bundle_json)
    bundle = _load_json_payload(bundle_path)
    summary = summarize_policy_dsl(bundle)
    failures = evaluate_gate(
        summary,
        min_rule_total=max(0, int(args.min_rule_total)),
        require_policy_version=bool(int(args.require_policy_version)),
        max_missing_rule_id_total=max(0, int(args.max_missing_rule_id_total)),
        max_duplicate_rule_id_total=max(0, int(args.max_duplicate_rule_id_total)),
        max_invalid_priority_total=max(0, int(args.max_invalid_priority_total)),
        max_invalid_action_total=max(0, int(args.max_invalid_action_total)),
        max_empty_condition_total=max(0, int(args.max_empty_condition_total)),
        max_unknown_condition_key_total=max(0, int(args.max_unknown_condition_key_total)),
        max_invalid_risk_level_total=max(0, int(args.max_invalid_risk_level_total)),
        max_invalid_reliability_level_total=max(0, int(args.max_invalid_reliability_level_total)),
        max_invalid_locale_total=max(0, int(args.max_invalid_locale_total)),
        max_invalid_effective_window_total=max(0, int(args.max_invalid_effective_window_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_missing_rule_id_total_increase=max(0, int(args.max_missing_rule_id_total_increase)),
            max_duplicate_rule_id_total_increase=max(0, int(args.max_duplicate_rule_id_total_increase)),
            max_invalid_priority_total_increase=max(0, int(args.max_invalid_priority_total_increase)),
            max_invalid_action_total_increase=max(0, int(args.max_invalid_action_total_increase)),
            max_empty_condition_total_increase=max(0, int(args.max_empty_condition_total_increase)),
            max_unknown_condition_key_total_increase=max(0, int(args.max_unknown_condition_key_total_increase)),
            max_invalid_risk_level_total_increase=max(0, int(args.max_invalid_risk_level_total_increase)),
            max_invalid_reliability_level_total_increase=max(0, int(args.max_invalid_reliability_level_total_increase)),
            max_invalid_locale_total_increase=max(0, int(args.max_invalid_locale_total_increase)),
            max_invalid_effective_window_total_increase=max(0, int(args.max_invalid_effective_window_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_json": str(bundle_path),
        "source": {
            "bundle_json": str(bundle_path),
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
                "require_policy_version": bool(int(args.require_policy_version)),
                "max_missing_rule_id_total": int(args.max_missing_rule_id_total),
                "max_duplicate_rule_id_total": int(args.max_duplicate_rule_id_total),
                "max_invalid_priority_total": int(args.max_invalid_priority_total),
                "max_invalid_action_total": int(args.max_invalid_action_total),
                "max_empty_condition_total": int(args.max_empty_condition_total),
                "max_unknown_condition_key_total": int(args.max_unknown_condition_key_total),
                "max_invalid_risk_level_total": int(args.max_invalid_risk_level_total),
                "max_invalid_reliability_level_total": int(args.max_invalid_reliability_level_total),
                "max_invalid_locale_total": int(args.max_invalid_locale_total),
                "max_invalid_effective_window_total": int(args.max_invalid_effective_window_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_missing_rule_id_total_increase": int(args.max_missing_rule_id_total_increase),
                "max_duplicate_rule_id_total_increase": int(args.max_duplicate_rule_id_total_increase),
                "max_invalid_priority_total_increase": int(args.max_invalid_priority_total_increase),
                "max_invalid_action_total_increase": int(args.max_invalid_action_total_increase),
                "max_empty_condition_total_increase": int(args.max_empty_condition_total_increase),
                "max_unknown_condition_key_total_increase": int(args.max_unknown_condition_key_total_increase),
                "max_invalid_risk_level_total_increase": int(args.max_invalid_risk_level_total_increase),
                "max_invalid_reliability_level_total_increase": int(args.max_invalid_reliability_level_total_increase),
                "max_invalid_locale_total_increase": int(args.max_invalid_locale_total_increase),
                "max_invalid_effective_window_total_increase": int(args.max_invalid_effective_window_total_increase),
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
    print(f"policy_version={summary.get('policy_version') or ''}")
    print(f"rule_total={_safe_int(summary.get('rule_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
