#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REQUIRED_FIELDS = ("correction_id", "domain", "trigger_pattern", "approved_answer", "owner")
VALID_APPROVAL_STATES = {"APPROVED", "ACTIVE", "ROLLED_BACK", "EXPIRED", "DRAFT", "PENDING_REVIEW"}


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
    for key in ("timestamp", "updated_at", "created_at", "approved_at", "activated_at", "generated_at"):
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


def _approval_state(row: Mapping[str, Any]) -> str:
    text = str(row.get("approval_state") or row.get("status") or "").strip().upper()
    aliases = {"APPROVE": "APPROVED", "ENABLE": "ACTIVE", "ENABLED": "ACTIVE", "ROLLBACK": "ROLLED_BACK"}
    return aliases.get(text, text or "UNKNOWN")


def _is_active(row: Mapping[str, Any], approval_state: str) -> bool:
    if _safe_bool(row.get("is_active"), False):
        return True
    return approval_state == "ACTIVE"


def _scope_key(row: Mapping[str, Any]) -> str:
    locale = str(row.get("locale") or "all").strip().lower() or "all"
    channel = str(row.get("channel") or "all").strip().lower() or "all"
    intent = str(row.get("intent") or "all").strip().lower() or "all"
    return f"{locale}:{channel}:{intent}"


def summarize_correction_memory_schema(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    record_total = 0
    active_total = 0
    missing_required_total = 0
    missing_scope_total = 0
    invalid_approval_state_total = 0
    unapproved_active_total = 0
    expired_active_total = 0
    duplicate_active_pattern_total = 0

    active_pattern_keys: set[str] = set()
    duplicate_keys: set[str] = set()

    for row in rows:
        record_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        missing_required = False
        for field in REQUIRED_FIELDS:
            if not str(row.get(field) or "").strip():
                missing_required = True
                break
        if missing_required:
            missing_required_total += 1

        locale = str(row.get("locale") or "").strip()
        channel = str(row.get("channel") or "").strip()
        intent = str(row.get("intent") or "").strip()
        if not locale or not channel or not intent:
            missing_scope_total += 1

        approval_state = _approval_state(row)
        if approval_state not in VALID_APPROVAL_STATES:
            invalid_approval_state_total += 1

        active = _is_active(row, approval_state)
        if not active:
            continue
        active_total += 1

        if approval_state not in {"APPROVED", "ACTIVE"}:
            unapproved_active_total += 1

        expiry_ts = _parse_ts(row.get("expiry") or row.get("expires_at"))
        if expiry_ts is not None and expiry_ts < now_dt:
            expired_active_total += 1

        key = "|".join(
            [
                str(row.get("domain") or "").strip().lower(),
                str(row.get("trigger_pattern") or "").strip().lower(),
                _scope_key(row),
            ]
        )
        if key in active_pattern_keys:
            duplicate_keys.add(key)
        else:
            active_pattern_keys.add(key)

    duplicate_active_pattern_total = len(duplicate_keys)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "record_total": record_total,
        "active_total": active_total,
        "missing_required_total": missing_required_total,
        "missing_scope_total": missing_scope_total,
        "invalid_approval_state_total": invalid_approval_state_total,
        "unapproved_active_total": unapproved_active_total,
        "expired_active_total": expired_active_total,
        "duplicate_active_pattern_total": duplicate_active_pattern_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_record_total: int,
    max_missing_required_total: int,
    max_missing_scope_total: int,
    max_invalid_approval_state_total: int,
    max_unapproved_active_total: int,
    max_expired_active_total: int,
    max_duplicate_active_pattern_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    record_total = _safe_int(summary.get("record_total"), 0)
    missing_required_total = _safe_int(summary.get("missing_required_total"), 0)
    missing_scope_total = _safe_int(summary.get("missing_scope_total"), 0)
    invalid_approval_state_total = _safe_int(summary.get("invalid_approval_state_total"), 0)
    unapproved_active_total = _safe_int(summary.get("unapproved_active_total"), 0)
    expired_active_total = _safe_int(summary.get("expired_active_total"), 0)
    duplicate_active_pattern_total = _safe_int(summary.get("duplicate_active_pattern_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat correction memory schema window too small: {window_size} < {int(min_window)}")
    if record_total < max(0, int(min_record_total)):
        failures.append(f"chat correction memory record total too small: {record_total} < {int(min_record_total)}")
    if window_size == 0:
        return failures

    if missing_required_total > max(0, int(max_missing_required_total)):
        failures.append(
            f"chat correction memory missing required total exceeded: {missing_required_total} > {int(max_missing_required_total)}"
        )
    if missing_scope_total > max(0, int(max_missing_scope_total)):
        failures.append(f"chat correction memory missing scope total exceeded: {missing_scope_total} > {int(max_missing_scope_total)}")
    if invalid_approval_state_total > max(0, int(max_invalid_approval_state_total)):
        failures.append(
            "chat correction memory invalid approval state total exceeded: "
            f"{invalid_approval_state_total} > {int(max_invalid_approval_state_total)}"
        )
    if unapproved_active_total > max(0, int(max_unapproved_active_total)):
        failures.append(
            f"chat correction memory unapproved active total exceeded: {unapproved_active_total} > {int(max_unapproved_active_total)}"
        )
    if expired_active_total > max(0, int(max_expired_active_total)):
        failures.append(
            f"chat correction memory expired active total exceeded: {expired_active_total} > {int(max_expired_active_total)}"
        )
    if duplicate_active_pattern_total > max(0, int(max_duplicate_active_pattern_total)):
        failures.append(
            "chat correction memory duplicate active pattern total exceeded: "
            f"{duplicate_active_pattern_total} > {int(max_duplicate_active_pattern_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat correction memory schema stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Correction Memory Schema")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- record_total: {_safe_int(summary.get('record_total'), 0)}")
    lines.append(f"- active_total: {_safe_int(summary.get('active_total'), 0)}")
    lines.append(f"- missing_required_total: {_safe_int(summary.get('missing_required_total'), 0)}")
    lines.append(f"- duplicate_active_pattern_total: {_safe_int(summary.get('duplicate_active_pattern_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat correction memory schema quality.")
    parser.add_argument("--events-jsonl", default="var/chat_correction/correction_memory_records.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_correction_memory_schema")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-record-total", type=int, default=0)
    parser.add_argument("--max-missing-required-total", type=int, default=0)
    parser.add_argument("--max-missing-scope-total", type=int, default=0)
    parser.add_argument("--max-invalid-approval-state-total", type=int, default=0)
    parser.add_argument("--max-unapproved-active-total", type=int, default=0)
    parser.add_argument("--max-expired-active-total", type=int, default=0)
    parser.add_argument("--max-duplicate-active-pattern-total", type=int, default=0)
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
    summary = summarize_correction_memory_schema(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_record_total=max(0, int(args.min_record_total)),
        max_missing_required_total=max(0, int(args.max_missing_required_total)),
        max_missing_scope_total=max(0, int(args.max_missing_scope_total)),
        max_invalid_approval_state_total=max(0, int(args.max_invalid_approval_state_total)),
        max_unapproved_active_total=max(0, int(args.max_unapproved_active_total)),
        max_expired_active_total=max(0, int(args.max_expired_active_total)),
        max_duplicate_active_pattern_total=max(0, int(args.max_duplicate_active_pattern_total)),
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
                "min_record_total": int(args.min_record_total),
                "max_missing_required_total": int(args.max_missing_required_total),
                "max_missing_scope_total": int(args.max_missing_scope_total),
                "max_invalid_approval_state_total": int(args.max_invalid_approval_state_total),
                "max_unapproved_active_total": int(args.max_unapproved_active_total),
                "max_expired_active_total": int(args.max_expired_active_total),
                "max_duplicate_active_pattern_total": int(args.max_duplicate_active_pattern_total),
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
    print(f"record_total={_safe_int(summary.get('record_total'), 0)}")
    print(f"missing_required_total={_safe_int(summary.get('missing_required_total'), 0)}")
    print(f"duplicate_active_pattern_total={_safe_int(summary.get('duplicate_active_pattern_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
