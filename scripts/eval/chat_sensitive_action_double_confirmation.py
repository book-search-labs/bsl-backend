#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SENSITIVE_INTENTS = {"CANCEL_ORDER", "REFUND_REQUEST", "ADDRESS_CHANGE", "PAYMENT_CHANGE"}
TWO_STEP_RISKS = {"MEDIUM", "HIGH", "WRITE_SENSITIVE"}


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


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "request": "REQUESTED",
        "requested": "REQUESTED",
        "confirm_step1_requested": "CONFIRM_STEP1_REQUESTED",
        "confirm1_requested": "CONFIRM_STEP1_REQUESTED",
        "confirm_1_requested": "CONFIRM_STEP1_REQUESTED",
        "confirm_step1_received": "CONFIRM_STEP1_CONFIRMED",
        "confirm1_received": "CONFIRM_STEP1_CONFIRMED",
        "confirm_1_received": "CONFIRM_STEP1_CONFIRMED",
        "confirm_step2_requested": "CONFIRM_STEP2_REQUESTED",
        "confirm2_requested": "CONFIRM_STEP2_REQUESTED",
        "confirm_2_requested": "CONFIRM_STEP2_REQUESTED",
        "confirm_step2_received": "CONFIRM_STEP2_CONFIRMED",
        "confirm2_received": "CONFIRM_STEP2_CONFIRMED",
        "confirm_2_received": "CONFIRM_STEP2_CONFIRMED",
        "token_issued": "TOKEN_ISSUED",
        "confirmation_token_issued": "TOKEN_ISSUED",
        "token_validated": "TOKEN_VALIDATED",
        "confirmation_token_validated": "TOKEN_VALIDATED",
        "token_reused": "TOKEN_REUSED",
        "confirmation_token_reused": "TOKEN_REUSED",
        "token_mismatch": "TOKEN_MISMATCH",
        "confirmation_token_mismatch": "TOKEN_MISMATCH",
        "token_expired": "TOKEN_EXPIRED",
        "confirmation_token_expired": "TOKEN_EXPIRED",
        "execute": "EXECUTED",
        "executed": "EXECUTED",
        "abort": "ABORTED",
        "aborted": "ABORTED",
        "cancelled": "ABORTED",
        "canceled": "ABORTED",
    }
    normalized = aliases.get(text, text.upper() or "UNKNOWN")
    return normalized


def _normalize_risk(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "L": "LOW",
        "M": "MEDIUM",
        "H": "HIGH",
        "WRITE": "MEDIUM",
    }
    return aliases.get(text, text or "UNKNOWN")


def _action_id(row: Mapping[str, Any]) -> str:
    for key in ("action_id", "workflow_id", "request_id", "id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _is_sensitive(row: Mapping[str, Any]) -> bool:
    intent = str(row.get("intent") or row.get("action_type") or "").strip().upper()
    risk = _normalize_risk(row.get("risk_level") or row.get("risk"))
    return intent in SENSITIVE_INTENTS or risk in {"MEDIUM", "HIGH", "WRITE_SENSITIVE"}


def _requires_two_step(row: Mapping[str, Any]) -> bool:
    risk = _normalize_risk(row.get("risk_level") or row.get("risk"))
    return risk in TWO_STEP_RISKS


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


def summarize_double_confirmation(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in events:
        action_id = _action_id(row)
        if not action_id:
            continue
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        grouped.setdefault(action_id, []).append(
            {
                "event": _normalize_event(row.get("event_type") or row.get("event") or row.get("status")),
                "risk": _normalize_risk(row.get("risk_level") or row.get("risk")),
                "sensitive": _is_sensitive(row),
                "requires_two_step": _requires_two_step(row),
                "ts": ts,
            }
        )

    sensitive_action_total = 0
    two_step_required_total = 0
    executed_total = 0
    execute_without_double_confirmation_total = 0
    token_issued_total = 0
    token_validated_total = 0
    token_reuse_total = 0
    token_mismatch_total = 0
    token_expired_total = 0
    token_missing_on_execute_total = 0

    for rows in grouped.values():
        ordered = sorted(
            rows,
            key=lambda item: item["ts"] if isinstance(item["ts"], datetime) else datetime.min.replace(tzinfo=timezone.utc),
        )
        sensitive = any(bool(item.get("sensitive")) for item in ordered)
        requires_two_step = any(bool(item.get("requires_two_step")) for item in ordered)
        if sensitive:
            sensitive_action_total += 1
        if sensitive and requires_two_step:
            two_step_required_total += 1

        step1_confirmed = False
        step2_confirmed = False
        token_validated = False
        for item in ordered:
            event = str(item.get("event") or "UNKNOWN")
            if event == "CONFIRM_STEP1_CONFIRMED":
                step1_confirmed = True
            elif event == "CONFIRM_STEP2_CONFIRMED":
                step2_confirmed = True
            elif event == "TOKEN_ISSUED":
                token_issued_total += 1
            elif event == "TOKEN_VALIDATED":
                token_validated_total += 1
                token_validated = True
            elif event == "TOKEN_REUSED":
                token_reuse_total += 1
            elif event == "TOKEN_MISMATCH":
                token_mismatch_total += 1
            elif event == "TOKEN_EXPIRED":
                token_expired_total += 1
            elif event == "EXECUTED":
                executed_total += 1
                if sensitive and requires_two_step and (not step1_confirmed or not step2_confirmed):
                    execute_without_double_confirmation_total += 1
                if sensitive and requires_two_step and not token_validated:
                    token_missing_on_execute_total += 1

    token_validation_ratio = (
        1.0 if token_issued_total == 0 else float(token_validated_total) / float(token_issued_total)
    )
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "action_total": len(grouped),
        "sensitive_action_total": sensitive_action_total,
        "two_step_required_total": two_step_required_total,
        "executed_total": executed_total,
        "execute_without_double_confirmation_total": execute_without_double_confirmation_total,
        "token_issued_total": token_issued_total,
        "token_validated_total": token_validated_total,
        "token_validation_ratio": token_validation_ratio,
        "token_reuse_total": token_reuse_total,
        "token_mismatch_total": token_mismatch_total,
        "token_expired_total": token_expired_total,
        "token_missing_on_execute_total": token_missing_on_execute_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_execute_without_double_confirmation_total: int,
    max_token_missing_on_execute_total: int,
    max_token_reuse_total: int,
    max_token_mismatch_total: int,
    max_token_expired_total: int,
    min_token_validation_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    execute_without_double_confirmation_total = _safe_int(summary.get("execute_without_double_confirmation_total"), 0)
    token_missing_on_execute_total = _safe_int(summary.get("token_missing_on_execute_total"), 0)
    token_reuse_total = _safe_int(summary.get("token_reuse_total"), 0)
    token_mismatch_total = _safe_int(summary.get("token_mismatch_total"), 0)
    token_expired_total = _safe_int(summary.get("token_expired_total"), 0)
    token_validation_ratio = _safe_float(summary.get("token_validation_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"sensitive double-confirmation window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if execute_without_double_confirmation_total > max(0, int(max_execute_without_double_confirmation_total)):
        failures.append(
            "execute without double confirmation total exceeded: "
            f"{execute_without_double_confirmation_total} > {int(max_execute_without_double_confirmation_total)}"
        )
    if token_missing_on_execute_total > max(0, int(max_token_missing_on_execute_total)):
        failures.append(
            "execute without validated confirmation token total exceeded: "
            f"{token_missing_on_execute_total} > {int(max_token_missing_on_execute_total)}"
        )
    if token_reuse_total > max(0, int(max_token_reuse_total)):
        failures.append(f"confirmation token reuse total exceeded: {token_reuse_total} > {int(max_token_reuse_total)}")
    if token_mismatch_total > max(0, int(max_token_mismatch_total)):
        failures.append(
            f"confirmation token mismatch total exceeded: {token_mismatch_total} > {int(max_token_mismatch_total)}"
        )
    if token_expired_total > max(0, int(max_token_expired_total)):
        failures.append(f"confirmation token expired total exceeded: {token_expired_total} > {int(max_token_expired_total)}")
    if token_validation_ratio < max(0.0, float(min_token_validation_ratio)):
        failures.append(
            f"confirmation token validation ratio below threshold: {token_validation_ratio:.4f} < {float(min_token_validation_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"sensitive double-confirmation events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_execute_without_double_confirmation_total_increase: int,
    max_token_missing_on_execute_total_increase: int,
    max_token_reuse_total_increase: int,
    max_token_mismatch_total_increase: int,
    max_token_expired_total_increase: int,
    max_token_validation_ratio_drop: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_execute_without_double_confirmation_total = _safe_int(
        base_summary.get("execute_without_double_confirmation_total"), 0
    )
    cur_execute_without_double_confirmation_total = _safe_int(
        current_summary.get("execute_without_double_confirmation_total"), 0
    )
    execute_without_double_confirmation_total_increase = max(
        0,
        cur_execute_without_double_confirmation_total - base_execute_without_double_confirmation_total,
    )
    if execute_without_double_confirmation_total_increase > max(
        0, int(max_execute_without_double_confirmation_total_increase)
    ):
        failures.append(
            "execute without double confirmation total regression: "
            f"baseline={base_execute_without_double_confirmation_total}, "
            f"current={cur_execute_without_double_confirmation_total}, "
            f"allowed_increase={max(0, int(max_execute_without_double_confirmation_total_increase))}"
        )

    base_token_missing_on_execute_total = _safe_int(base_summary.get("token_missing_on_execute_total"), 0)
    cur_token_missing_on_execute_total = _safe_int(current_summary.get("token_missing_on_execute_total"), 0)
    token_missing_on_execute_total_increase = max(
        0,
        cur_token_missing_on_execute_total - base_token_missing_on_execute_total,
    )
    if token_missing_on_execute_total_increase > max(0, int(max_token_missing_on_execute_total_increase)):
        failures.append(
            "token missing on execute total regression: "
            f"baseline={base_token_missing_on_execute_total}, current={cur_token_missing_on_execute_total}, "
            f"allowed_increase={max(0, int(max_token_missing_on_execute_total_increase))}"
        )

    base_token_reuse_total = _safe_int(base_summary.get("token_reuse_total"), 0)
    cur_token_reuse_total = _safe_int(current_summary.get("token_reuse_total"), 0)
    token_reuse_total_increase = max(0, cur_token_reuse_total - base_token_reuse_total)
    if token_reuse_total_increase > max(0, int(max_token_reuse_total_increase)):
        failures.append(
            "token reuse total regression: "
            f"baseline={base_token_reuse_total}, current={cur_token_reuse_total}, "
            f"allowed_increase={max(0, int(max_token_reuse_total_increase))}"
        )

    base_token_mismatch_total = _safe_int(base_summary.get("token_mismatch_total"), 0)
    cur_token_mismatch_total = _safe_int(current_summary.get("token_mismatch_total"), 0)
    token_mismatch_total_increase = max(0, cur_token_mismatch_total - base_token_mismatch_total)
    if token_mismatch_total_increase > max(0, int(max_token_mismatch_total_increase)):
        failures.append(
            "token mismatch total regression: "
            f"baseline={base_token_mismatch_total}, current={cur_token_mismatch_total}, "
            f"allowed_increase={max(0, int(max_token_mismatch_total_increase))}"
        )

    base_token_expired_total = _safe_int(base_summary.get("token_expired_total"), 0)
    cur_token_expired_total = _safe_int(current_summary.get("token_expired_total"), 0)
    token_expired_total_increase = max(0, cur_token_expired_total - base_token_expired_total)
    if token_expired_total_increase > max(0, int(max_token_expired_total_increase)):
        failures.append(
            "token expired total regression: "
            f"baseline={base_token_expired_total}, current={cur_token_expired_total}, "
            f"allowed_increase={max(0, int(max_token_expired_total_increase))}"
        )

    base_token_validation_ratio = _safe_float(base_summary.get("token_validation_ratio"), 1.0)
    cur_token_validation_ratio = _safe_float(current_summary.get("token_validation_ratio"), 1.0)
    token_validation_ratio_drop = max(0.0, base_token_validation_ratio - cur_token_validation_ratio)
    if token_validation_ratio_drop > max(0.0, float(max_token_validation_ratio_drop)):
        failures.append(
            "token validation ratio regression: "
            f"baseline={base_token_validation_ratio:.6f}, current={cur_token_validation_ratio:.6f}, "
            f"allowed_drop={float(max_token_validation_ratio_drop):.6f}"
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
    lines.append("# Chat Sensitive Action Double Confirmation")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- action_total: {_safe_int(summary.get('action_total'), 0)}")
    lines.append(f"- two_step_required_total: {_safe_int(summary.get('two_step_required_total'), 0)}")
    lines.append(
        f"- execute_without_double_confirmation_total: {_safe_int(summary.get('execute_without_double_confirmation_total'), 0)}"
    )
    lines.append(f"- token_reuse_total: {_safe_int(summary.get('token_reuse_total'), 0)}")
    lines.append(f"- token_validation_ratio: {_safe_float(summary.get('token_validation_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate two-step confirmation and one-time token policy.")
    parser.add_argument("--events-jsonl", default="var/chat_actions/sensitive_action_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_sensitive_action_double_confirmation")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-execute-without-double-confirmation-total", type=int, default=0)
    parser.add_argument("--max-token-missing-on-execute-total", type=int, default=0)
    parser.add_argument("--max-token-reuse-total", type=int, default=0)
    parser.add_argument("--max-token-mismatch-total", type=int, default=0)
    parser.add_argument("--max-token-expired-total", type=int, default=0)
    parser.add_argument("--min-token-validation-ratio", type=float, default=0.95)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-execute-without-double-confirmation-total-increase", type=int, default=0)
    parser.add_argument("--max-token-missing-on-execute-total-increase", type=int, default=0)
    parser.add_argument("--max-token-reuse-total-increase", type=int, default=0)
    parser.add_argument("--max-token-mismatch-total-increase", type=int, default=0)
    parser.add_argument("--max-token-expired-total-increase", type=int, default=0)
    parser.add_argument("--max-token-validation-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_double_confirmation(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_execute_without_double_confirmation_total=max(0, int(args.max_execute_without_double_confirmation_total)),
        max_token_missing_on_execute_total=max(0, int(args.max_token_missing_on_execute_total)),
        max_token_reuse_total=max(0, int(args.max_token_reuse_total)),
        max_token_mismatch_total=max(0, int(args.max_token_mismatch_total)),
        max_token_expired_total=max(0, int(args.max_token_expired_total)),
        min_token_validation_ratio=max(0.0, float(args.min_token_validation_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_execute_without_double_confirmation_total_increase=max(
                0, int(args.max_execute_without_double_confirmation_total_increase)
            ),
            max_token_missing_on_execute_total_increase=max(0, int(args.max_token_missing_on_execute_total_increase)),
            max_token_reuse_total_increase=max(0, int(args.max_token_reuse_total_increase)),
            max_token_mismatch_total_increase=max(0, int(args.max_token_mismatch_total_increase)),
            max_token_expired_total_increase=max(0, int(args.max_token_expired_total_increase)),
            max_token_validation_ratio_drop=max(0.0, float(args.max_token_validation_ratio_drop)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
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
                "max_execute_without_double_confirmation_total": int(args.max_execute_without_double_confirmation_total),
                "max_token_missing_on_execute_total": int(args.max_token_missing_on_execute_total),
                "max_token_reuse_total": int(args.max_token_reuse_total),
                "max_token_mismatch_total": int(args.max_token_mismatch_total),
                "max_token_expired_total": int(args.max_token_expired_total),
                "min_token_validation_ratio": float(args.min_token_validation_ratio),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_execute_without_double_confirmation_total_increase": int(
                    args.max_execute_without_double_confirmation_total_increase
                ),
                "max_token_missing_on_execute_total_increase": int(args.max_token_missing_on_execute_total_increase),
                "max_token_reuse_total_increase": int(args.max_token_reuse_total_increase),
                "max_token_mismatch_total_increase": int(args.max_token_mismatch_total_increase),
                "max_token_expired_total_increase": int(args.max_token_expired_total_increase),
                "max_token_validation_ratio_drop": float(args.max_token_validation_ratio_drop),
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
    print(f"two_step_required_total={_safe_int(summary.get('two_step_required_total'), 0)}")
    print(
        "execute_without_double_confirmation_total="
        f"{_safe_int(summary.get('execute_without_double_confirmation_total'), 0)}"
    )
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
