#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_ACTIONS = {"MASK", "BLOCK", "REVIEW", "ALLOW"}
ALLOWED_PII_TYPES = {"EMAIL", "PHONE", "ADDRESS", "ACCOUNT", "CARD", "NAME", "ID", "DEVICE"}


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


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "MASKED": "MASK",
        "BLOCKED": "BLOCK",
        "REDACT": "MASK",
        "ESCALATE": "REVIEW",
        "MANUAL_REVIEW": "REVIEW",
        "PASS": "ALLOW",
    }
    if text in VALID_ACTIONS:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _extract_pii_types(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    direct = row.get("pii_type")
    if isinstance(direct, str):
        values.append(direct)
    listed = row.get("pii_types")
    if isinstance(listed, (list, tuple)):
        for item in listed:
            values.append(str(item))
    detections = row.get("detections")
    if isinstance(detections, (list, tuple)):
        for item in detections:
            if isinstance(item, Mapping):
                values.append(str(item.get("type") or item.get("pii_type") or ""))

    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip().upper()
        if not text:
            continue
        normalized.append(text)
    return normalized


def _detected(row: Mapping[str, Any], pii_types: list[str]) -> bool:
    if pii_types:
        return True
    if _safe_bool(row.get("pii_detected"), False):
        return True
    return _safe_int(row.get("detection_count"), 0) > 0


def summarize_dlp_filter(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    detected_total = 0
    blocked_total = 0
    masked_total = 0
    review_total = 0
    allowed_total = 0
    invalid_action_total = 0
    unknown_pii_type_total = 0
    unmasked_violation_total = 0
    false_positive_total = 0
    missing_reason_total = 0

    pii_type_distribution: dict[str, int] = {}

    for row in rows:
        run_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        pii_types = _extract_pii_types(row)
        for pii_type in pii_types:
            pii_type_distribution[pii_type] = pii_type_distribution.get(pii_type, 0) + 1
            if pii_type not in ALLOWED_PII_TYPES:
                unknown_pii_type_total += 1

        if not _detected(row, pii_types):
            continue
        detected_total += 1

        action = _normalize_action(row.get("action") or row.get("policy_action"))
        if action == "BLOCK":
            blocked_total += 1
        elif action == "MASK":
            masked_total += 1
        elif action == "REVIEW":
            review_total += 1
        elif action == "ALLOW":
            allowed_total += 1
            if not _safe_bool(row.get("override_approved"), False):
                unmasked_violation_total += 1
        else:
            invalid_action_total += 1
            unmasked_violation_total += 1

        if _safe_bool(row.get("false_positive"), False):
            false_positive_total += 1
        reason = str(row.get("reason_code") or row.get("policy_reason") or "").strip()
        if not reason:
            missing_reason_total += 1

    protected_total = blocked_total + masked_total + review_total
    protected_action_ratio = 1.0 if detected_total == 0 else float(protected_total) / float(detected_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "detected_total": detected_total,
        "blocked_total": blocked_total,
        "masked_total": masked_total,
        "review_total": review_total,
        "allowed_total": allowed_total,
        "protected_action_ratio": protected_action_ratio,
        "invalid_action_total": invalid_action_total,
        "unknown_pii_type_total": unknown_pii_type_total,
        "unmasked_violation_total": unmasked_violation_total,
        "false_positive_total": false_positive_total,
        "missing_reason_total": missing_reason_total,
        "pii_type_distribution": [
            {"pii_type": key, "count": value} for key, value in sorted(pii_type_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_detected_total: int,
    min_protected_action_ratio: float,
    max_unmasked_violation_total: int,
    max_invalid_action_total: int,
    max_unknown_pii_type_total: int,
    max_false_positive_total: int,
    max_missing_reason_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    detected_total = _safe_int(summary.get("detected_total"), 0)
    protected_action_ratio = _safe_float(summary.get("protected_action_ratio"), 0.0)
    unmasked_violation_total = _safe_int(summary.get("unmasked_violation_total"), 0)
    invalid_action_total = _safe_int(summary.get("invalid_action_total"), 0)
    unknown_pii_type_total = _safe_int(summary.get("unknown_pii_type_total"), 0)
    false_positive_total = _safe_int(summary.get("false_positive_total"), 0)
    missing_reason_total = _safe_int(summary.get("missing_reason_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat privacy dlp window too small: {window_size} < {int(min_window)}")
    if detected_total < max(0, int(min_detected_total)):
        failures.append(f"chat privacy dlp detected total too small: {detected_total} < {int(min_detected_total)}")
    if window_size == 0:
        return failures

    if protected_action_ratio < max(0.0, float(min_protected_action_ratio)):
        failures.append(
            "chat privacy dlp protected action ratio below minimum: "
            f"{protected_action_ratio:.4f} < {float(min_protected_action_ratio):.4f}"
        )
    if unmasked_violation_total > max(0, int(max_unmasked_violation_total)):
        failures.append(
            f"chat privacy dlp unmasked violation total exceeded: {unmasked_violation_total} > {int(max_unmasked_violation_total)}"
        )
    if invalid_action_total > max(0, int(max_invalid_action_total)):
        failures.append(f"chat privacy dlp invalid action total exceeded: {invalid_action_total} > {int(max_invalid_action_total)}")
    if unknown_pii_type_total > max(0, int(max_unknown_pii_type_total)):
        failures.append(
            f"chat privacy dlp unknown pii type total exceeded: {unknown_pii_type_total} > {int(max_unknown_pii_type_total)}"
        )
    if false_positive_total > max(0, int(max_false_positive_total)):
        failures.append(f"chat privacy dlp false positive total exceeded: {false_positive_total} > {int(max_false_positive_total)}")
    if missing_reason_total > max(0, int(max_missing_reason_total)):
        failures.append(f"chat privacy dlp missing reason total exceeded: {missing_reason_total} > {int(max_missing_reason_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat privacy dlp stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Privacy DLP Filter")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- detected_total: {_safe_int(summary.get('detected_total'), 0)}")
    lines.append(f"- blocked_total: {_safe_int(summary.get('blocked_total'), 0)}")
    lines.append(f"- masked_total: {_safe_int(summary.get('masked_total'), 0)}")
    lines.append(f"- review_total: {_safe_int(summary.get('review_total'), 0)}")
    lines.append(f"- unmasked_violation_total: {_safe_int(summary.get('unmasked_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat real-time DLP filter effectiveness.")
    parser.add_argument("--events-jsonl", default="var/chat_privacy/dlp_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_privacy_dlp_filter")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-detected-total", type=int, default=0)
    parser.add_argument("--min-protected-action-ratio", type=float, default=0.0)
    parser.add_argument("--max-unmasked-violation-total", type=int, default=0)
    parser.add_argument("--max-invalid-action-total", type=int, default=0)
    parser.add_argument("--max-unknown-pii-type-total", type=int, default=0)
    parser.add_argument("--max-false-positive-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_dlp_filter(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_detected_total=max(0, int(args.min_detected_total)),
        min_protected_action_ratio=max(0.0, float(args.min_protected_action_ratio)),
        max_unmasked_violation_total=max(0, int(args.max_unmasked_violation_total)),
        max_invalid_action_total=max(0, int(args.max_invalid_action_total)),
        max_unknown_pii_type_total=max(0, int(args.max_unknown_pii_type_total)),
        max_false_positive_total=max(0, int(args.max_false_positive_total)),
        max_missing_reason_total=max(0, int(args.max_missing_reason_total)),
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
                "min_detected_total": int(args.min_detected_total),
                "min_protected_action_ratio": float(args.min_protected_action_ratio),
                "max_unmasked_violation_total": int(args.max_unmasked_violation_total),
                "max_invalid_action_total": int(args.max_invalid_action_total),
                "max_unknown_pii_type_total": int(args.max_unknown_pii_type_total),
                "max_false_positive_total": int(args.max_false_positive_total),
                "max_missing_reason_total": int(args.max_missing_reason_total),
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
    print(f"detected_total={_safe_int(summary.get('detected_total'), 0)}")
    print(f"unmasked_violation_total={_safe_int(summary.get('unmasked_violation_total'), 0)}")
    print(f"false_positive_total={_safe_int(summary.get('false_positive_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
