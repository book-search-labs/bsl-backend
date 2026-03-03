#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


MASK_TOKENS = ("***", "***", "[REDACTED]", "REDACTED", "MASKED", "XXXX", "****")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DIGIT_PATTERN = re.compile(r"\d")


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


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


def _read_jsonl(path: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, Mapping):
            rows.append({str(k): v for k, v in item.items()})
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def _escalated(row: Mapping[str, Any]) -> bool:
    if row.get("escalated") is not None:
        return _safe_bool(row.get("escalated"))
    if row.get("escalation_triggered") is not None:
        return _safe_bool(row.get("escalation_triggered"))
    level = str(row.get("escalation_level") or "").strip().upper()
    return level not in {"", "NONE", "NO_ESCALATION"}


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("handover_payload")
    if isinstance(payload, Mapping):
        return payload
    return {}


def _summary_present(row: Mapping[str, Any]) -> bool:
    payload = _payload(row)
    value = payload.get("summary")
    if value is None:
        value = payload.get("conversation_summary")
    if value is None:
        value = row.get("handover_summary")
    return bool(str(value or "").strip())


def _actions_present(row: Mapping[str, Any]) -> bool:
    payload = _payload(row)
    actions = payload.get("executed_actions")
    if isinstance(actions, list):
        return len(actions) > 0
    row_actions = row.get("executed_actions")
    if isinstance(row_actions, list):
        return len(row_actions) > 0
    return bool(str(payload.get("action_log") or "").strip())


def _policy_evidence_present(row: Mapping[str, Any]) -> bool:
    payload = _payload(row)
    evidence = payload.get("policy_evidence")
    if isinstance(evidence, list):
        return len(evidence) > 0
    if evidence is not None and str(evidence).strip():
        return True
    reasons = row.get("policy_reason_codes")
    if isinstance(reasons, list):
        return len(reasons) > 0
    return bool(str(row.get("policy_basis") or "").strip())


def _payload_present(row: Mapping[str, Any]) -> bool:
    if row.get("handover_payload_present") is not None:
        return _safe_bool(row.get("handover_payload_present"))
    payload = _payload(row)
    if payload:
        return True
    return _summary_present(row) or _actions_present(row) or _policy_evidence_present(row)


def _is_masked(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    upper = text.upper()
    if any(token in upper for token in MASK_TOKENS):
        return True
    if "@" in text and EMAIL_PATTERN.match(text):
        local = text.split("@", 1)[0]
        if "*" in local or "x" in local.lower():
            return True
        return False
    digits = DIGIT_PATTERN.findall(text)
    if len(digits) >= 8:
        return False
    return True


def _masking_violated(row: Mapping[str, Any]) -> bool:
    payload = _payload(row)
    sensitive_values: list[str] = []

    for key in ("customer_phone", "customer_email", "customer_address", "payment_id", "card_number"):
        value = payload.get(key)
        if value is None:
            value = row.get(key)
        if value is None:
            continue
        sensitive_values.append(str(value))

    sensitive_map = payload.get("sensitive_fields")
    if isinstance(sensitive_map, Mapping):
        for value in sensitive_map.values():
            sensitive_values.append(str(value))

    for value in sensitive_values:
        if not _is_masked(value):
            return True
    return False


def summarize_case_handover_payload_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    escalation_total = 0
    payload_present_total = 0
    payload_missing_total = 0
    summary_missing_total = 0
    actions_missing_total = 0
    policy_evidence_missing_total = 0
    masking_violation_total = 0
    complete_payload_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _escalated(row):
            continue
        escalation_total += 1

        payload_present = _payload_present(row)
        summary_present = _summary_present(row)
        actions_present = _actions_present(row)
        policy_present = _policy_evidence_present(row)

        if payload_present:
            payload_present_total += 1
        else:
            payload_missing_total += 1

        if not summary_present:
            summary_missing_total += 1
        if not actions_present:
            actions_missing_total += 1
        if not policy_present:
            policy_evidence_missing_total += 1

        masking_violation = _masking_violated(row)
        if masking_violation:
            masking_violation_total += 1

        if payload_present and summary_present and actions_present and policy_present and not masking_violation:
            complete_payload_total += 1

    payload_completeness_ratio = 1.0 if escalation_total == 0 else float(complete_payload_total) / float(escalation_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "escalation_total": escalation_total,
        "payload_present_total": payload_present_total,
        "payload_missing_total": payload_missing_total,
        "summary_missing_total": summary_missing_total,
        "actions_missing_total": actions_missing_total,
        "policy_evidence_missing_total": policy_evidence_missing_total,
        "masking_violation_total": masking_violation_total,
        "complete_payload_total": complete_payload_total,
        "payload_completeness_ratio": payload_completeness_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_payload_completeness_ratio: float,
    max_payload_missing_total: int,
    max_summary_missing_total: int,
    max_actions_missing_total: int,
    max_policy_evidence_missing_total: int,
    max_masking_violation_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    payload_completeness_ratio = _safe_float(summary.get("payload_completeness_ratio"), 0.0)
    payload_missing_total = _safe_int(summary.get("payload_missing_total"), 0)
    summary_missing_total = _safe_int(summary.get("summary_missing_total"), 0)
    actions_missing_total = _safe_int(summary.get("actions_missing_total"), 0)
    policy_evidence_missing_total = _safe_int(summary.get("policy_evidence_missing_total"), 0)
    masking_violation_total = _safe_int(summary.get("masking_violation_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"handover payload window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"handover payload event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if payload_completeness_ratio < max(0.0, float(min_payload_completeness_ratio)):
        failures.append(
            f"handover payload completeness ratio below minimum: {payload_completeness_ratio:.4f} < {float(min_payload_completeness_ratio):.4f}"
        )
    if payload_missing_total > max(0, int(max_payload_missing_total)):
        failures.append(f"handover payload missing total exceeded: {payload_missing_total} > {int(max_payload_missing_total)}")
    if summary_missing_total > max(0, int(max_summary_missing_total)):
        failures.append(f"handover summary missing total exceeded: {summary_missing_total} > {int(max_summary_missing_total)}")
    if actions_missing_total > max(0, int(max_actions_missing_total)):
        failures.append(f"handover actions missing total exceeded: {actions_missing_total} > {int(max_actions_missing_total)}")
    if policy_evidence_missing_total > max(0, int(max_policy_evidence_missing_total)):
        failures.append(
            f"handover policy evidence missing total exceeded: {policy_evidence_missing_total} > {int(max_policy_evidence_missing_total)}"
        )
    if masking_violation_total > max(0, int(max_masking_violation_total)):
        failures.append(f"handover masking violation total exceeded: {masking_violation_total} > {int(max_masking_violation_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"handover payload stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Case Handover Payload Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- payload_completeness_ratio: {_safe_float(summary.get('payload_completeness_ratio'), 0.0):.4f}")
    lines.append(f"- payload_missing_total: {_safe_int(summary.get('payload_missing_total'), 0)}")
    lines.append(f"- summary_missing_total: {_safe_int(summary.get('summary_missing_total'), 0)}")
    lines.append(f"- actions_missing_total: {_safe_int(summary.get('actions_missing_total'), 0)}")
    lines.append(f"- policy_evidence_missing_total: {_safe_int(summary.get('policy_evidence_missing_total'), 0)}")
    lines.append(f"- masking_violation_total: {_safe_int(summary.get('masking_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate case handover payload quality for escalations.")
    parser.add_argument("--events-jsonl", default="var/dialog_planner/handover_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_case_handover_payload_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-payload-completeness-ratio", type=float, default=0.0)
    parser.add_argument("--max-payload-missing-total", type=int, default=1000000)
    parser.add_argument("--max-summary-missing-total", type=int, default=1000000)
    parser.add_argument("--max-actions-missing-total", type=int, default=1000000)
    parser.add_argument("--max-policy-evidence-missing-total", type=int, default=1000000)
    parser.add_argument("--max-masking-violation-total", type=int, default=1000000)
    parser.add_argument("--max-stale-minutes", type=float, default=1000000.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_case_handover_payload_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_payload_completeness_ratio=max(0.0, float(args.min_payload_completeness_ratio)),
        max_payload_missing_total=max(0, int(args.max_payload_missing_total)),
        max_summary_missing_total=max(0, int(args.max_summary_missing_total)),
        max_actions_missing_total=max(0, int(args.max_actions_missing_total)),
        max_policy_evidence_missing_total=max(0, int(args.max_policy_evidence_missing_total)),
        max_masking_violation_total=max(0, int(args.max_masking_violation_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_payload_completeness_ratio": float(args.min_payload_completeness_ratio),
                "max_payload_missing_total": int(args.max_payload_missing_total),
                "max_summary_missing_total": int(args.max_summary_missing_total),
                "max_actions_missing_total": int(args.max_actions_missing_total),
                "max_policy_evidence_missing_total": int(args.max_policy_evidence_missing_total),
                "max_masking_violation_total": int(args.max_masking_violation_total),
                "max_stale_minutes": float(args.max_stale_minutes),
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
    print(f"payload_completeness_ratio={_safe_float(summary.get('payload_completeness_ratio'), 0.0):.4f}")
    print(f"payload_missing_total={_safe_int(summary.get('payload_missing_total'), 0)}")
    print(f"masking_violation_total={_safe_int(summary.get('masking_violation_total'), 0)}")
    print(f"summary_missing_total={_safe_int(summary.get('summary_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
