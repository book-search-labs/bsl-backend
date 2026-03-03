#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SENSITIVE_INTENT_DEFAULTS = {
    "CANCEL_ORDER",
    "REFUND_REQUEST",
    "ADDRESS_CHANGE",
    "PAYMENT_CHANGE",
}
ALLOW_DECISIONS = {"ALLOW", "EXECUTE", "PROCEED"}
SAFE_DECISIONS = {"BLOCK", "ESCALATE", "HUMAN_HANDOFF", "ASK_CONFIRMATION", "DEFER"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_reliability(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"H": "HIGH", "M": "MEDIUM", "L": "LOW"}
    if text in {"HIGH", "MEDIUM", "LOW"}:
        return text
    return aliases.get(text, text)


def _normalize_decision(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "DENY": "BLOCK",
        "REJECT": "BLOCK",
        "HANDOFF": "HUMAN_HANDOFF",
        "TRANSFER": "HUMAN_HANDOFF",
        "CONFIRM": "ASK_CONFIRMATION",
    }
    return aliases.get(text, text or "UNKNOWN")


def _normalize_intent(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_sensitive(row: Mapping[str, Any], sensitive_intents: set[str]) -> bool:
    intent = _normalize_intent(row.get("intent") or row.get("action_type"))
    risk_level = str(row.get("risk_level") or "").strip().upper()
    if intent in sensitive_intents:
        return True
    return risk_level in {"WRITE", "WRITE_SENSITIVE"}


def read_events(path: Path, *, window_hours: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
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

    threshold = (now or datetime.now(timezone.utc)) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def summarize_guardrail(
    events: list[Mapping[str, Any]],
    *,
    sensitive_intents: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    low_sensitive_total = 0
    low_sensitive_block_total = 0
    low_sensitive_execute_total = 0
    invalid_decision_total = 0
    missing_policy_version_total = 0
    missing_reason_code_total = 0
    intents: dict[str, int] = {}
    policy_versions: set[str] = set()

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        reliability = _normalize_reliability(row.get("reliability_level"))
        decision = _normalize_decision(row.get("decision") or row.get("guardrail_action") or row.get("action"))
        intent = _normalize_intent(row.get("intent") or row.get("action_type"))
        policy_version = str(
            row.get("trust_policy_version")
            or row.get("policy_version")
            or row.get("trust_formula_version")
            or ""
        ).strip()
        reason_code = str(row.get("reason_code") or "").strip()

        if policy_version:
            policy_versions.add(policy_version)
        else:
            missing_policy_version_total += 1
        if not reason_code:
            missing_reason_code_total += 1

        if decision not in ALLOW_DECISIONS and decision not in SAFE_DECISIONS:
            invalid_decision_total += 1

        if reliability == "LOW" and _is_sensitive(row, sensitive_intents):
            low_sensitive_total += 1
            intents[intent or "UNKNOWN"] = intents.get(intent or "UNKNOWN", 0) + 1
            if decision in ALLOW_DECISIONS:
                low_sensitive_execute_total += 1
            elif decision in SAFE_DECISIONS:
                low_sensitive_block_total += 1

    low_sensitive_guardrail_ratio = (
        1.0 if low_sensitive_total == 0 else float(low_sensitive_block_total) / float(low_sensitive_total)
    )
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "low_sensitive_total": low_sensitive_total,
        "low_sensitive_block_total": low_sensitive_block_total,
        "low_sensitive_execute_total": low_sensitive_execute_total,
        "low_sensitive_guardrail_ratio": low_sensitive_guardrail_ratio,
        "invalid_decision_total": invalid_decision_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_reason_code_total": missing_reason_code_total,
        "policy_version_total": len(policy_versions),
        "intent_distribution": [{"intent": key, "count": value} for key, value in sorted(intents.items(), key=lambda x: x[0])],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_low_sensitive_execute_total: int,
    min_low_sensitive_guardrail_ratio: float,
    max_invalid_decision_total: int,
    max_missing_policy_version_total: int,
    max_missing_reason_code_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    low_sensitive_execute_total = _safe_int(summary.get("low_sensitive_execute_total"), 0)
    low_sensitive_guardrail_ratio = _safe_float(summary.get("low_sensitive_guardrail_ratio"), 1.0)
    invalid_decision_total = _safe_int(summary.get("invalid_decision_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"low reliability guardrail window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if low_sensitive_execute_total > max(0, int(max_low_sensitive_execute_total)):
        failures.append(
            "low reliability sensitive execute total exceeded: "
            f"{low_sensitive_execute_total} > {int(max_low_sensitive_execute_total)}"
        )
    if low_sensitive_guardrail_ratio < max(0.0, float(min_low_sensitive_guardrail_ratio)):
        failures.append(
            "low reliability guardrail ratio below threshold: "
            f"{low_sensitive_guardrail_ratio:.4f} < {float(min_low_sensitive_guardrail_ratio):.4f}"
        )
    if invalid_decision_total > max(0, int(max_invalid_decision_total)):
        failures.append(f"invalid guardrail decision total exceeded: {invalid_decision_total} > {int(max_invalid_decision_total)}")
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "missing trust policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"low reliability guardrail events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_low_sensitive_execute_total_increase: int,
    max_low_sensitive_guardrail_ratio_drop: float,
    max_invalid_decision_total_increase: int,
    max_missing_policy_version_total_increase: int,
    max_missing_reason_code_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_low_sensitive_execute_total = _safe_int(base_summary.get("low_sensitive_execute_total"), 0)
    cur_low_sensitive_execute_total = _safe_int(current_summary.get("low_sensitive_execute_total"), 0)
    low_sensitive_execute_total_increase = max(0, cur_low_sensitive_execute_total - base_low_sensitive_execute_total)
    if low_sensitive_execute_total_increase > max(0, int(max_low_sensitive_execute_total_increase)):
        failures.append(
            "low sensitive execute total regression: "
            f"baseline={base_low_sensitive_execute_total}, current={cur_low_sensitive_execute_total}, "
            f"allowed_increase={max(0, int(max_low_sensitive_execute_total_increase))}"
        )

    base_low_sensitive_guardrail_ratio = _safe_float(base_summary.get("low_sensitive_guardrail_ratio"), 1.0)
    cur_low_sensitive_guardrail_ratio = _safe_float(current_summary.get("low_sensitive_guardrail_ratio"), 1.0)
    low_sensitive_guardrail_ratio_drop = max(0.0, base_low_sensitive_guardrail_ratio - cur_low_sensitive_guardrail_ratio)
    if low_sensitive_guardrail_ratio_drop > max(0.0, float(max_low_sensitive_guardrail_ratio_drop)):
        failures.append(
            "low sensitive guardrail ratio regression: "
            f"baseline={base_low_sensitive_guardrail_ratio:.6f}, current={cur_low_sensitive_guardrail_ratio:.6f}, "
            f"allowed_drop={float(max_low_sensitive_guardrail_ratio_drop):.6f}"
        )

    base_invalid_decision_total = _safe_int(base_summary.get("invalid_decision_total"), 0)
    cur_invalid_decision_total = _safe_int(current_summary.get("invalid_decision_total"), 0)
    invalid_decision_total_increase = max(0, cur_invalid_decision_total - base_invalid_decision_total)
    if invalid_decision_total_increase > max(0, int(max_invalid_decision_total_increase)):
        failures.append(
            "invalid decision total regression: "
            f"baseline={base_invalid_decision_total}, current={cur_invalid_decision_total}, "
            f"allowed_increase={max(0, int(max_invalid_decision_total_increase))}"
        )

    base_missing_policy_version_total = _safe_int(base_summary.get("missing_policy_version_total"), 0)
    cur_missing_policy_version_total = _safe_int(current_summary.get("missing_policy_version_total"), 0)
    missing_policy_version_total_increase = max(
        0, cur_missing_policy_version_total - base_missing_policy_version_total
    )
    if missing_policy_version_total_increase > max(0, int(max_missing_policy_version_total_increase)):
        failures.append(
            "missing policy version total regression: "
            f"baseline={base_missing_policy_version_total}, current={cur_missing_policy_version_total}, "
            f"allowed_increase={max(0, int(max_missing_policy_version_total_increase))}"
        )

    base_missing_reason_code_total = _safe_int(base_summary.get("missing_reason_code_total"), 0)
    cur_missing_reason_code_total = _safe_int(current_summary.get("missing_reason_code_total"), 0)
    missing_reason_code_total_increase = max(0, cur_missing_reason_code_total - base_missing_reason_code_total)
    if missing_reason_code_total_increase > max(0, int(max_missing_reason_code_total_increase)):
        failures.append(
            "missing reason code total regression: "
            f"baseline={base_missing_reason_code_total}, current={cur_missing_reason_code_total}, "
            f"allowed_increase={max(0, int(max_missing_reason_code_total_increase))}"
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
    lines.append("# Chat Low Reliability Guardrail")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- low_sensitive_total: {_safe_int(summary.get('low_sensitive_total'), 0)}")
    lines.append(f"- low_sensitive_block_total: {_safe_int(summary.get('low_sensitive_block_total'), 0)}")
    lines.append(f"- low_sensitive_execute_total: {_safe_int(summary.get('low_sensitive_execute_total'), 0)}")
    lines.append(f"- low_sensitive_guardrail_ratio: {_safe_float(summary.get('low_sensitive_guardrail_ratio'), 1.0):.4f}")
    lines.append(f"- missing_policy_version_total: {_safe_int(summary.get('missing_policy_version_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate low-reliability sensitive-action guardrail enforcement.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/guardrail_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument(
        "--sensitive-intents",
        default="CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE",
    )
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_low_reliability_guardrail")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-low-sensitive-execute-total", type=int, default=0)
    parser.add_argument("--min-low-sensitive-guardrail-ratio", type=float, default=1.0)
    parser.add_argument("--max-invalid-decision-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-low-sensitive-execute-total-increase", type=int, default=0)
    parser.add_argument("--max-low-sensitive-guardrail-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-invalid-decision-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def _parse_sensitive_intents(value: str) -> set[str]:
    parsed = {token.strip().upper() for token in str(value or "").split(",") if token.strip()}
    if not parsed:
        return set(SENSITIVE_INTENT_DEFAULTS)
    return parsed


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    sensitive_intents = _parse_sensitive_intents(args.sensitive_intents)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_guardrail(events, sensitive_intents=sensitive_intents)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_low_sensitive_execute_total=max(0, int(args.max_low_sensitive_execute_total)),
        min_low_sensitive_guardrail_ratio=max(0.0, float(args.min_low_sensitive_guardrail_ratio)),
        max_invalid_decision_total=max(0, int(args.max_invalid_decision_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_low_sensitive_execute_total_increase=max(0, int(args.max_low_sensitive_execute_total_increase)),
            max_low_sensitive_guardrail_ratio_drop=max(0.0, float(args.max_low_sensitive_guardrail_ratio_drop)),
            max_invalid_decision_total_increase=max(0, int(args.max_invalid_decision_total_increase)),
            max_missing_policy_version_total_increase=max(0, int(args.max_missing_policy_version_total_increase)),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
            "sensitive_intents": sorted(sensitive_intents),
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
                "min_window": int(args.min_window),
                "max_low_sensitive_execute_total": int(args.max_low_sensitive_execute_total),
                "min_low_sensitive_guardrail_ratio": float(args.min_low_sensitive_guardrail_ratio),
                "max_invalid_decision_total": int(args.max_invalid_decision_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_low_sensitive_execute_total_increase": int(args.max_low_sensitive_execute_total_increase),
                "max_low_sensitive_guardrail_ratio_drop": float(args.max_low_sensitive_guardrail_ratio_drop),
                "max_invalid_decision_total_increase": int(args.max_invalid_decision_total_increase),
                "max_missing_policy_version_total_increase": int(args.max_missing_policy_version_total_increase),
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
    print(f"low_sensitive_total={_safe_int(summary.get('low_sensitive_total'), 0)}")
    print(f"low_sensitive_execute_total={_safe_int(summary.get('low_sensitive_execute_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
