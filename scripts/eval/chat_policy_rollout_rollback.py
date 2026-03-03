#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "policy_publish": "POLICY_PUBLISH",
        "publish": "POLICY_PUBLISH",
        "policy_promote": "POLICY_PROMOTE",
        "promote": "POLICY_PROMOTE",
        "policy_rollback": "POLICY_ROLLBACK",
        "rollback": "POLICY_ROLLBACK",
        "policy_activate": "POLICY_ACTIVATE",
        "activate": "POLICY_ACTIVATE",
        "policy_rollout_failed": "POLICY_ROLLOUT_FAILED",
        "rollout_failed": "POLICY_ROLLOUT_FAILED",
        "policy_validate_failed": "POLICY_ROLLOUT_FAILED",
        "validate_failed": "POLICY_ROLLOUT_FAILED",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _as_versions(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


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
        if isinstance(payload, Mapping):
            rows.append({str(k): v for k, v in payload.items()})
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


def summarize_policy_rollout(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    publish_total = 0
    promote_total = 0
    rollback_total = 0
    activate_total = 0
    rollout_failure_total = 0

    missing_policy_version_total = 0
    promote_without_approval_total = 0
    checksum_missing_total = 0
    rollback_to_unknown_version_total = 0
    active_version_conflict_total = 0

    seen_versions: set[str] = set()

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event == "UNKNOWN":
            continue

        policy_version = str(row.get("policy_version") or row.get("version") or "").strip()
        if not policy_version:
            missing_policy_version_total += 1

        checksum = str(row.get("checksum") or row.get("bundle_checksum") or "").strip()
        if event in {"POLICY_PUBLISH", "POLICY_PROMOTE", "POLICY_ROLLBACK"} and not checksum:
            checksum_missing_total += 1

        if event == "POLICY_PUBLISH":
            publish_total += 1
            if policy_version:
                seen_versions.add(policy_version)
        elif event == "POLICY_PROMOTE":
            promote_total += 1
            approved_by = str(row.get("approved_by") or row.get("approver") or "").strip()
            if not approved_by:
                promote_without_approval_total += 1
            if policy_version:
                seen_versions.add(policy_version)
        elif event == "POLICY_ROLLBACK":
            rollback_total += 1
            target_version = str(row.get("rollback_to_version") or row.get("target_version") or "").strip()
            if target_version and target_version not in seen_versions:
                rollback_to_unknown_version_total += 1
            if policy_version:
                seen_versions.add(policy_version)
        elif event == "POLICY_ACTIVATE":
            activate_total += 1
            active_versions = _as_versions(row.get("active_versions") or row.get("active_version"))
            if len(active_versions) > 1:
                active_version_conflict_total += 1
        elif event == "POLICY_ROLLOUT_FAILED":
            rollout_failure_total += 1

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "publish_total": publish_total,
        "promote_total": promote_total,
        "rollback_total": rollback_total,
        "activate_total": activate_total,
        "rollout_failure_total": rollout_failure_total,
        "missing_policy_version_total": missing_policy_version_total,
        "promote_without_approval_total": promote_without_approval_total,
        "checksum_missing_total": checksum_missing_total,
        "rollback_to_unknown_version_total": rollback_to_unknown_version_total,
        "active_version_conflict_total": active_version_conflict_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_policy_version_total: int,
    max_promote_without_approval_total: int,
    max_checksum_missing_total: int,
    max_rollback_to_unknown_version_total: int,
    max_active_version_conflict_total: int,
    max_rollout_failure_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    promote_without_approval_total = _safe_int(summary.get("promote_without_approval_total"), 0)
    checksum_missing_total = _safe_int(summary.get("checksum_missing_total"), 0)
    rollback_to_unknown_version_total = _safe_int(summary.get("rollback_to_unknown_version_total"), 0)
    active_version_conflict_total = _safe_int(summary.get("active_version_conflict_total"), 0)
    rollout_failure_total = _safe_int(summary.get("rollout_failure_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"policy rollout window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            f"policy rollout missing policy version total exceeded: {missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if promote_without_approval_total > max(0, int(max_promote_without_approval_total)):
        failures.append(
            "policy rollout promote without approval total exceeded: "
            f"{promote_without_approval_total} > {int(max_promote_without_approval_total)}"
        )
    if checksum_missing_total > max(0, int(max_checksum_missing_total)):
        failures.append(f"policy rollout checksum missing total exceeded: {checksum_missing_total} > {int(max_checksum_missing_total)}")
    if rollback_to_unknown_version_total > max(0, int(max_rollback_to_unknown_version_total)):
        failures.append(
            "policy rollout rollback-to-unknown total exceeded: "
            f"{rollback_to_unknown_version_total} > {int(max_rollback_to_unknown_version_total)}"
        )
    if active_version_conflict_total > max(0, int(max_active_version_conflict_total)):
        failures.append(
            "policy rollout active version conflict total exceeded: "
            f"{active_version_conflict_total} > {int(max_active_version_conflict_total)}"
        )
    if rollout_failure_total > max(0, int(max_rollout_failure_total)):
        failures.append(
            f"policy rollout failure total exceeded: {rollout_failure_total} > {int(max_rollout_failure_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"policy rollout events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Policy Rollout Rollback")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- publish_total: {_safe_int(summary.get('publish_total'), 0)}")
    lines.append(f"- promote_total: {_safe_int(summary.get('promote_total'), 0)}")
    lines.append(f"- rollback_total: {_safe_int(summary.get('rollback_total'), 0)}")
    lines.append(f"- rollout_failure_total: {_safe_int(summary.get('rollout_failure_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate policy rollout and rollback governance signals.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/policy_rollout_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_policy_rollout_rollback")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-promote-without-approval-total", type=int, default=0)
    parser.add_argument("--max-checksum-missing-total", type=int, default=0)
    parser.add_argument("--max-rollback-to-unknown-version-total", type=int, default=0)
    parser.add_argument("--max-active-version-conflict-total", type=int, default=0)
    parser.add_argument("--max-rollout-failure-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
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
    summary = summarize_policy_rollout(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_promote_without_approval_total=max(0, int(args.max_promote_without_approval_total)),
        max_checksum_missing_total=max(0, int(args.max_checksum_missing_total)),
        max_rollback_to_unknown_version_total=max(0, int(args.max_rollback_to_unknown_version_total)),
        max_active_version_conflict_total=max(0, int(args.max_active_version_conflict_total)),
        max_rollout_failure_total=max(0, int(args.max_rollout_failure_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_promote_without_approval_total": int(args.max_promote_without_approval_total),
                "max_checksum_missing_total": int(args.max_checksum_missing_total),
                "max_rollback_to_unknown_version_total": int(args.max_rollback_to_unknown_version_total),
                "max_active_version_conflict_total": int(args.max_active_version_conflict_total),
                "max_rollout_failure_total": int(args.max_rollout_failure_total),
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
    print(f"promote_total={_safe_int(summary.get('promote_total'), 0)}")
    print(f"rollback_total={_safe_int(summary.get('rollback_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
