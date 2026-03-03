#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _rotation_event(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("key_rotation"), False):
        return True
    event_type = str(row.get("event_type") or "").strip().lower()
    if event_type in {"key_rotated", "signing_key_rotated", "rotation_completed", "rotation_started"}:
        return True
    return bool(str(row.get("rotation_id") or "").strip())


def _rotation_success(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("rotation_success"), False):
        return True
    event_type = str(row.get("event_type") or "").strip().lower()
    if event_type in {"key_rotated", "signing_key_rotated", "rotation_completed"}:
        return True
    status = str(row.get("status") or "").strip().lower()
    return status in {"success", "completed", "rotated"}


def _unauthorized_key_access(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("unauthorized_key_access"), False):
        return True
    access_decision = str(row.get("access_decision") or "").strip().lower()
    return access_decision in {"deny", "blocked", "forbidden"}


def _least_privilege_violation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("least_privilege_violation"), False):
        return True
    return _safe_bool(row.get("scope_violation"), False)


def _deprecated_key_sign(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("deprecated_key_used_for_signing"), False):
        return True
    key_state = str(row.get("signing_key_state") or "").strip().lower()
    return key_state in {"deprecated", "retired"}


def _kms_sync_failed(row: Mapping[str, Any]) -> bool:
    if "kms_sync_ok" in row:
        return not _safe_bool(row.get("kms_sync_ok"), True)
    return _safe_bool(row.get("kms_sync_failed"), False)


def _audit_logged(row: Mapping[str, Any]) -> bool:
    if "audit_logged" in row:
        return _safe_bool(row.get("audit_logged"), False)
    return bool(str(row.get("audit_id") or row.get("audit_event_id") or "").strip())


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("rotation_reason_code") or "").strip())


def summarize_prompt_signing_key_rotation_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    key_rotation_total = 0
    key_rotation_success_total = 0
    key_rotation_failed_total = 0
    unauthorized_key_access_total = 0
    least_privilege_violation_total = 0
    deprecated_key_sign_total = 0
    kms_sync_failed_total = 0
    audit_log_missing_total = 0
    reason_code_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        rotation = _rotation_event(row)
        rotation_success = _rotation_success(row)
        unauthorized_access = _unauthorized_key_access(row)
        privilege_violation = _least_privilege_violation(row)
        deprecated_sign = _deprecated_key_sign(row)
        kms_sync_failed = _kms_sync_failed(row)
        audit_logged = _audit_logged(row)
        reason_present = _reason_present(row)

        if rotation:
            key_rotation_total += 1
            if rotation_success:
                key_rotation_success_total += 1
            else:
                key_rotation_failed_total += 1

        if unauthorized_access:
            unauthorized_key_access_total += 1
        if privilege_violation:
            least_privilege_violation_total += 1
        if deprecated_sign:
            deprecated_key_sign_total += 1
        if kms_sync_failed:
            kms_sync_failed_total += 1
        if not audit_logged:
            audit_log_missing_total += 1
        if (rotation or unauthorized_access or privilege_violation or deprecated_sign or kms_sync_failed) and not reason_present:
            reason_code_missing_total += 1

    key_rotation_success_ratio = (
        1.0 if key_rotation_total == 0 else float(key_rotation_success_total) / float(key_rotation_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "key_rotation_total": key_rotation_total,
        "key_rotation_success_total": key_rotation_success_total,
        "key_rotation_success_ratio": key_rotation_success_ratio,
        "key_rotation_failed_total": key_rotation_failed_total,
        "unauthorized_key_access_total": unauthorized_key_access_total,
        "least_privilege_violation_total": least_privilege_violation_total,
        "deprecated_key_sign_total": deprecated_key_sign_total,
        "kms_sync_failed_total": kms_sync_failed_total,
        "audit_log_missing_total": audit_log_missing_total,
        "reason_code_missing_total": reason_code_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_key_rotation_total: int,
    min_key_rotation_success_ratio: float,
    max_key_rotation_failed_total: int,
    max_unauthorized_key_access_total: int,
    max_least_privilege_violation_total: int,
    max_deprecated_key_sign_total: int,
    max_kms_sync_failed_total: int,
    max_audit_log_missing_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    key_rotation_total = _safe_int(summary.get("key_rotation_total"), 0)
    key_rotation_success_ratio = _safe_float(summary.get("key_rotation_success_ratio"), 0.0)
    key_rotation_failed_total = _safe_int(summary.get("key_rotation_failed_total"), 0)
    unauthorized_key_access_total = _safe_int(summary.get("unauthorized_key_access_total"), 0)
    least_privilege_violation_total = _safe_int(summary.get("least_privilege_violation_total"), 0)
    deprecated_key_sign_total = _safe_int(summary.get("deprecated_key_sign_total"), 0)
    kms_sync_failed_total = _safe_int(summary.get("kms_sync_failed_total"), 0)
    audit_log_missing_total = _safe_int(summary.get("audit_log_missing_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat prompt key rotation window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"chat prompt key rotation event total too small: {event_total} < {int(min_event_total)}")
    if key_rotation_total < max(0, int(min_key_rotation_total)):
        failures.append(
            f"chat prompt key rotation total too small: {key_rotation_total} < {int(min_key_rotation_total)}"
        )
    if window_size == 0:
        return failures

    if key_rotation_success_ratio < max(0.0, float(min_key_rotation_success_ratio)):
        failures.append(
            f"chat prompt key rotation success ratio below minimum: {key_rotation_success_ratio:.4f} < {float(min_key_rotation_success_ratio):.4f}"
        )
    if key_rotation_failed_total > max(0, int(max_key_rotation_failed_total)):
        failures.append(
            f"chat prompt key rotation failed total exceeded: {key_rotation_failed_total} > {int(max_key_rotation_failed_total)}"
        )
    if unauthorized_key_access_total > max(0, int(max_unauthorized_key_access_total)):
        failures.append(
            "chat prompt unauthorized key access total exceeded: "
            f"{unauthorized_key_access_total} > {int(max_unauthorized_key_access_total)}"
        )
    if least_privilege_violation_total > max(0, int(max_least_privilege_violation_total)):
        failures.append(
            "chat prompt least-privilege violation total exceeded: "
            f"{least_privilege_violation_total} > {int(max_least_privilege_violation_total)}"
        )
    if deprecated_key_sign_total > max(0, int(max_deprecated_key_sign_total)):
        failures.append(
            f"chat prompt deprecated key sign total exceeded: {deprecated_key_sign_total} > {int(max_deprecated_key_sign_total)}"
        )
    if kms_sync_failed_total > max(0, int(max_kms_sync_failed_total)):
        failures.append(
            f"chat prompt KMS sync failed total exceeded: {kms_sync_failed_total} > {int(max_kms_sync_failed_total)}"
        )
    if audit_log_missing_total > max(0, int(max_audit_log_missing_total)):
        failures.append(
            f"chat prompt key audit-log missing total exceeded: {audit_log_missing_total} > {int(max_audit_log_missing_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat prompt key reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat prompt key rotation stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Prompt Signing Key Rotation Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- key_rotation_total: {_safe_int(summary.get('key_rotation_total'), 0)}")
    lines.append(f"- key_rotation_success_ratio: {_safe_float(summary.get('key_rotation_success_ratio'), 0.0):.4f}")
    lines.append(f"- unauthorized_key_access_total: {_safe_int(summary.get('unauthorized_key_access_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate prompt signing key rotation and access control guard.")
    parser.add_argument("--events-jsonl", default="var/chat_prompt_supply/key_rotation_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_prompt_signing_key_rotation_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-key-rotation-total", type=int, default=0)
    parser.add_argument("--min-key-rotation-success-ratio", type=float, default=0.0)
    parser.add_argument("--max-key-rotation-failed-total", type=int, default=1000000)
    parser.add_argument("--max-unauthorized-key-access-total", type=int, default=1000000)
    parser.add_argument("--max-least-privilege-violation-total", type=int, default=1000000)
    parser.add_argument("--max-deprecated-key-sign-total", type=int, default=1000000)
    parser.add_argument("--max-kms-sync-failed-total", type=int, default=1000000)
    parser.add_argument("--max-audit-log-missing-total", type=int, default=1000000)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=1000000)
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
    summary = summarize_prompt_signing_key_rotation_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_key_rotation_total=max(0, int(args.min_key_rotation_total)),
        min_key_rotation_success_ratio=max(0.0, float(args.min_key_rotation_success_ratio)),
        max_key_rotation_failed_total=max(0, int(args.max_key_rotation_failed_total)),
        max_unauthorized_key_access_total=max(0, int(args.max_unauthorized_key_access_total)),
        max_least_privilege_violation_total=max(0, int(args.max_least_privilege_violation_total)),
        max_deprecated_key_sign_total=max(0, int(args.max_deprecated_key_sign_total)),
        max_kms_sync_failed_total=max(0, int(args.max_kms_sync_failed_total)),
        max_audit_log_missing_total=max(0, int(args.max_audit_log_missing_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
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
                "min_key_rotation_total": int(args.min_key_rotation_total),
                "min_key_rotation_success_ratio": float(args.min_key_rotation_success_ratio),
                "max_key_rotation_failed_total": int(args.max_key_rotation_failed_total),
                "max_unauthorized_key_access_total": int(args.max_unauthorized_key_access_total),
                "max_least_privilege_violation_total": int(args.max_least_privilege_violation_total),
                "max_deprecated_key_sign_total": int(args.max_deprecated_key_sign_total),
                "max_kms_sync_failed_total": int(args.max_kms_sync_failed_total),
                "max_audit_log_missing_total": int(args.max_audit_log_missing_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
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
    print(f"event_total={_safe_int(summary.get('event_total'), 0)}")
    print(f"key_rotation_total={_safe_int(summary.get('key_rotation_total'), 0)}")
    print(f"unauthorized_key_access_total={_safe_int(summary.get('unauthorized_key_access_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
