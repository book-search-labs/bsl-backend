#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PURGED_STATUSES = {"PURGED", "DELETED", "REMOVED"}
EXPIRED_STATUSES = {"EXPIRED", "READY_TO_PURGE"}


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


def _status(row: Mapping[str, Any]) -> str:
    return str(row.get("status") or row.get("retention_status") or "").strip().upper()


def _is_purged(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("purged"), False):
        return True
    status = _status(row)
    if status in PURGED_STATUSES:
        return True
    action = str(row.get("action") or row.get("event_type") or "").strip().upper()
    return action in PURGED_STATUSES


def _is_expired(row: Mapping[str, Any], *, now: datetime) -> bool:
    if _safe_bool(row.get("expired"), False):
        return True
    status = _status(row)
    if status in EXPIRED_STATUSES:
        return True
    expires_at = _parse_ts(row.get("expires_at") or row.get("retention_expires_at"))
    if expires_at is not None:
        return expires_at <= now
    return False


def summarize_retention_enforcement(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    expired_total = 0
    purge_due_total = 0
    purged_total = 0
    purge_miss_total = 0
    legal_hold_total = 0
    hold_exempt_total = 0
    hold_violation_total = 0
    invalid_retention_policy_total = 0
    delete_audit_missing_total = 0
    data_type_distribution: dict[str, int] = {}

    for row in rows:
        run_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        data_type = str(row.get("data_type") or row.get("artifact_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
        data_type_distribution[data_type] = data_type_distribution.get(data_type, 0) + 1

        legal_hold = _safe_bool(row.get("legal_hold"), False) or _safe_bool(row.get("hold_active"), False)
        if legal_hold:
            legal_hold_total += 1

        expired = _is_expired(row, now=now_dt)
        purged = _is_purged(row)

        expires_at = _parse_ts(row.get("expires_at") or row.get("retention_expires_at"))
        retention_days = _safe_int(row.get("retention_days") or row.get("ttl_days"), 0)
        if expired and expires_at is None and retention_days <= 0:
            invalid_retention_policy_total += 1

        if expired:
            expired_total += 1

        if legal_hold and expired:
            hold_exempt_total += 1
        elif expired:
            purge_due_total += 1

        if purged:
            purged_total += 1
            audit_id = str(row.get("audit_id") or row.get("purge_job_id") or row.get("delete_audit_id") or "").strip()
            reason = str(row.get("reason_code") or row.get("purge_reason") or "").strip()
            if not audit_id or not reason:
                delete_audit_missing_total += 1

        if legal_hold and purged:
            hold_violation_total += 1

        if expired and not legal_hold and not purged:
            purge_miss_total += 1

    purge_coverage_ratio = 1.0 if purge_due_total == 0 else float(purged_total - hold_violation_total) / float(max(1, purge_due_total))
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "expired_total": expired_total,
        "purge_due_total": purge_due_total,
        "purged_total": purged_total,
        "purge_miss_total": purge_miss_total,
        "purge_coverage_ratio": purge_coverage_ratio,
        "legal_hold_total": legal_hold_total,
        "hold_exempt_total": hold_exempt_total,
        "hold_violation_total": hold_violation_total,
        "invalid_retention_policy_total": invalid_retention_policy_total,
        "delete_audit_missing_total": delete_audit_missing_total,
        "data_type_distribution": [
            {"data_type": key, "count": value} for key, value in sorted(data_type_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_expired_total: int,
    min_purge_coverage_ratio: float,
    max_purge_miss_total: int,
    max_hold_violation_total: int,
    max_invalid_retention_policy_total: int,
    max_delete_audit_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    expired_total = _safe_int(summary.get("expired_total"), 0)
    purge_coverage_ratio = _safe_float(summary.get("purge_coverage_ratio"), 0.0)
    purge_miss_total = _safe_int(summary.get("purge_miss_total"), 0)
    hold_violation_total = _safe_int(summary.get("hold_violation_total"), 0)
    invalid_retention_policy_total = _safe_int(summary.get("invalid_retention_policy_total"), 0)
    delete_audit_missing_total = _safe_int(summary.get("delete_audit_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat privacy retention window too small: {window_size} < {int(min_window)}")
    if expired_total < max(0, int(min_expired_total)):
        failures.append(f"chat privacy retention expired total too small: {expired_total} < {int(min_expired_total)}")
    if window_size == 0:
        return failures

    if purge_coverage_ratio < max(0.0, float(min_purge_coverage_ratio)):
        failures.append(
            "chat privacy retention purge coverage ratio below minimum: "
            f"{purge_coverage_ratio:.4f} < {float(min_purge_coverage_ratio):.4f}"
        )
    if purge_miss_total > max(0, int(max_purge_miss_total)):
        failures.append(f"chat privacy retention purge miss total exceeded: {purge_miss_total} > {int(max_purge_miss_total)}")
    if hold_violation_total > max(0, int(max_hold_violation_total)):
        failures.append(
            f"chat privacy retention hold violation total exceeded: {hold_violation_total} > {int(max_hold_violation_total)}"
        )
    if invalid_retention_policy_total > max(0, int(max_invalid_retention_policy_total)):
        failures.append(
            "chat privacy retention invalid policy total exceeded: "
            f"{invalid_retention_policy_total} > {int(max_invalid_retention_policy_total)}"
        )
    if delete_audit_missing_total > max(0, int(max_delete_audit_missing_total)):
        failures.append(
            "chat privacy retention delete audit missing total exceeded: "
            f"{delete_audit_missing_total} > {int(max_delete_audit_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat privacy retention stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Privacy Retention Enforcement")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- expired_total: {_safe_int(summary.get('expired_total'), 0)}")
    lines.append(f"- purge_due_total: {_safe_int(summary.get('purge_due_total'), 0)}")
    lines.append(f"- purged_total: {_safe_int(summary.get('purged_total'), 0)}")
    lines.append(f"- purge_miss_total: {_safe_int(summary.get('purge_miss_total'), 0)}")
    lines.append(f"- hold_violation_total: {_safe_int(summary.get('hold_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat retention policy enforcement and purge behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_privacy/retention_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_privacy_retention_enforcement")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-expired-total", type=int, default=0)
    parser.add_argument("--min-purge-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-purge-miss-total", type=int, default=0)
    parser.add_argument("--max-hold-violation-total", type=int, default=0)
    parser.add_argument("--max-invalid-retention-policy-total", type=int, default=0)
    parser.add_argument("--max-delete-audit-missing-total", type=int, default=0)
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
    summary = summarize_retention_enforcement(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_expired_total=max(0, int(args.min_expired_total)),
        min_purge_coverage_ratio=max(0.0, float(args.min_purge_coverage_ratio)),
        max_purge_miss_total=max(0, int(args.max_purge_miss_total)),
        max_hold_violation_total=max(0, int(args.max_hold_violation_total)),
        max_invalid_retention_policy_total=max(0, int(args.max_invalid_retention_policy_total)),
        max_delete_audit_missing_total=max(0, int(args.max_delete_audit_missing_total)),
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
                "min_expired_total": int(args.min_expired_total),
                "min_purge_coverage_ratio": float(args.min_purge_coverage_ratio),
                "max_purge_miss_total": int(args.max_purge_miss_total),
                "max_hold_violation_total": int(args.max_hold_violation_total),
                "max_invalid_retention_policy_total": int(args.max_invalid_retention_policy_total),
                "max_delete_audit_missing_total": int(args.max_delete_audit_missing_total),
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
    print(f"expired_total={_safe_int(summary.get('expired_total'), 0)}")
    print(f"purge_miss_total={_safe_int(summary.get('purge_miss_total'), 0)}")
    print(f"hold_violation_total={_safe_int(summary.get('hold_violation_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
