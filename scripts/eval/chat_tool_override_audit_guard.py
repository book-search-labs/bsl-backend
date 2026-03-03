#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


APPLIED_DECISIONS = {"APPLIED", "ENABLED", "ACTIVE", "SUCCESS", "ALLOW", "ALLOWED"}
DENIED_DECISIONS = {"DENY", "DENIED", "REJECT", "REJECTED", "BLOCK", "BLOCKED", "UNAUTHORIZED", "FORBID"}
FORCE_INCLUDE_TYPES = {"FORCE_INCLUDE", "PREFER", "PIN", "FORCE_USE"}
FORCE_EXCLUDE_TYPES = {"FORCE_EXCLUDE", "BLOCK", "DISABLE", "DENY", "SKIP"}


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


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return None


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


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


def _tool(row: Mapping[str, Any]) -> str:
    return str(row.get("tool") or row.get("selected_tool") or row.get("route_tool") or "").strip()


def _override_type(row: Mapping[str, Any]) -> str:
    token = _normalize_token(row.get("override_type") or row.get("strategy") or row.get("action"))
    if token in FORCE_INCLUDE_TYPES:
        return "FORCE_INCLUDE"
    if token in FORCE_EXCLUDE_TYPES:
        return "FORCE_EXCLUDE"
    if "INCLUDE" in token or "PREFER" in token or "PIN" in token:
        return "FORCE_INCLUDE"
    if "EXCLUDE" in token or "BLOCK" in token or "DISABLE" in token or "DENY" in token:
        return "FORCE_EXCLUDE"
    return token or "UNKNOWN"


def _decision(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("override_decision") or row.get("decision") or row.get("result") or row.get("status"))


def _is_applied(row: Mapping[str, Any], *, decision: str) -> bool:
    explicit = _safe_bool(row.get("override_applied"))
    if explicit is not None:
        return explicit
    if decision in APPLIED_DECISIONS:
        return True
    action = _normalize_token(row.get("action"))
    if action in {"APPLY", "ENABLE", "SET"} and decision not in DENIED_DECISIONS:
        return True
    return False


def _auth_allowed(row: Mapping[str, Any]) -> bool | None:
    for key in ("authz_allowed", "authorized", "policy_allowed"):
        explicit = _safe_bool(row.get(key))
        if explicit is not None:
            return explicit
    decision = _normalize_token(row.get("authz_decision") or row.get("authorization_decision"))
    if decision in {"ALLOW", "ALLOWED", "APPROVED", "PERMIT", "PERMITTED"}:
        return True
    if decision in DENIED_DECISIONS:
        return False
    return None


def _actor(row: Mapping[str, Any]) -> str:
    return str(
        row.get("actor_user_id")
        or row.get("operator_id")
        or row.get("actor")
        or row.get("updated_by")
        or row.get("user_id")
        or ""
    ).strip()


def _reason(row: Mapping[str, Any]) -> str:
    return str(row.get("reason") or row.get("override_reason") or row.get("note") or row.get("comment") or "").strip()


def _has_audit_context(row: Mapping[str, Any]) -> bool:
    trace_id = str(row.get("trace_id") or "").strip()
    request_id = str(row.get("request_id") or "").strip()
    return bool(trace_id and request_id)


def _has_expiry(row: Mapping[str, Any]) -> bool:
    if _parse_ts(row.get("expires_at")) is not None:
        return True
    for key in ("ttl_minutes", "duration_minutes", "expires_in_minutes"):
        if _safe_int(row.get(key), 0) > 0:
            return True
    return False


def summarize_tool_override_audit_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    override_event_total = 0
    override_applied_total = 0
    force_include_total = 0
    force_exclude_total = 0
    missing_actor_total = 0
    missing_reason_total = 0
    missing_audit_context_total = 0
    missing_expiry_total = 0
    unauthorized_override_total = 0
    distribution: dict[tuple[str, str, str], int] = {}
    by_tool_types: dict[str, set[str]] = {}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        tool = _tool(row) or "UNKNOWN"
        override_type = _override_type(row)
        decision = _decision(row)
        applied = _is_applied(row, decision=decision)
        auth_allowed = _auth_allowed(row)

        override_event_total += 1
        distribution[(tool, override_type, decision or "UNKNOWN")] = distribution.get(
            (tool, override_type, decision or "UNKNOWN"), 0
        ) + 1

        if applied:
            override_applied_total += 1

            if override_type == "FORCE_INCLUDE":
                force_include_total += 1
            if override_type == "FORCE_EXCLUDE":
                force_exclude_total += 1

            if not _actor(row):
                missing_actor_total += 1
            if not _reason(row):
                missing_reason_total += 1
            if not _has_audit_context(row):
                missing_audit_context_total += 1
            if not _has_expiry(row):
                missing_expiry_total += 1
            if auth_allowed is False or decision in DENIED_DECISIONS:
                unauthorized_override_total += 1

            if override_type in {"FORCE_INCLUDE", "FORCE_EXCLUDE"} and tool != "UNKNOWN":
                by_tool_types.setdefault(tool, set()).add(override_type)

    conflicting_override_total = 0
    for tool_types in by_tool_types.values():
        if {"FORCE_INCLUDE", "FORCE_EXCLUDE"}.issubset(tool_types):
            conflicting_override_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)
    override_distribution = [
        {"tool": tool, "override_type": override_type, "decision": decision, "count": count}
        for (tool, override_type, decision), count in sorted(distribution.items(), key=lambda item: item[0])
    ]

    return {
        "window_size": len(rows),
        "override_event_total": override_event_total,
        "override_applied_total": override_applied_total,
        "force_include_total": force_include_total,
        "force_exclude_total": force_exclude_total,
        "missing_actor_total": missing_actor_total,
        "missing_reason_total": missing_reason_total,
        "missing_audit_context_total": missing_audit_context_total,
        "missing_expiry_total": missing_expiry_total,
        "unauthorized_override_total": unauthorized_override_total,
        "conflicting_override_total": conflicting_override_total,
        "override_distribution": override_distribution,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_override_event_total: int,
    max_missing_actor_total: int,
    max_missing_reason_total: int,
    max_missing_audit_context_total: int,
    max_missing_expiry_total: int,
    max_unauthorized_override_total: int,
    max_conflicting_override_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    override_event_total = _safe_int(summary.get("override_event_total"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    missing_reason_total = _safe_int(summary.get("missing_reason_total"), 0)
    missing_audit_context_total = _safe_int(summary.get("missing_audit_context_total"), 0)
    missing_expiry_total = _safe_int(summary.get("missing_expiry_total"), 0)
    unauthorized_override_total = _safe_int(summary.get("unauthorized_override_total"), 0)
    conflicting_override_total = _safe_int(summary.get("conflicting_override_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool override audit window too small: {window_size} < {int(min_window)}")
    if override_event_total < max(0, int(min_override_event_total)):
        failures.append(
            f"tool override audit event total too small: {override_event_total} < {int(min_override_event_total)}"
        )
    if window_size == 0:
        return failures

    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"tool override audit missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if missing_reason_total > max(0, int(max_missing_reason_total)):
        failures.append(
            f"tool override audit missing reason total exceeded: {missing_reason_total} > {int(max_missing_reason_total)}"
        )
    if missing_audit_context_total > max(0, int(max_missing_audit_context_total)):
        failures.append(
            "tool override audit missing trace/request context total exceeded: "
            f"{missing_audit_context_total} > {int(max_missing_audit_context_total)}"
        )
    if missing_expiry_total > max(0, int(max_missing_expiry_total)):
        failures.append(
            f"tool override audit missing expiry total exceeded: {missing_expiry_total} > {int(max_missing_expiry_total)}"
        )
    if unauthorized_override_total > max(0, int(max_unauthorized_override_total)):
        failures.append(
            "tool override audit unauthorized override total exceeded: "
            f"{unauthorized_override_total} > {int(max_unauthorized_override_total)}"
        )
    if conflicting_override_total > max(0, int(max_conflicting_override_total)):
        failures.append(
            "tool override audit conflicting override total exceeded: "
            f"{conflicting_override_total} > {int(max_conflicting_override_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool override audit stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Override Audit Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- override_event_total: {_safe_int(summary.get('override_event_total'), 0)}")
    lines.append(f"- override_applied_total: {_safe_int(summary.get('override_applied_total'), 0)}")
    lines.append(f"- conflicting_override_total: {_safe_int(summary.get('conflicting_override_total'), 0)}")
    lines.append(f"- unauthorized_override_total: {_safe_int(summary.get('unauthorized_override_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool operator override audit quality.")
    parser.add_argument("--events-jsonl", default="var/tool_health/override_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_override_audit_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-override-event-total", type=int, default=0)
    parser.add_argument("--max-missing-actor-total", type=int, default=1000000)
    parser.add_argument("--max-missing-reason-total", type=int, default=1000000)
    parser.add_argument("--max-missing-audit-context-total", type=int, default=1000000)
    parser.add_argument("--max-missing-expiry-total", type=int, default=1000000)
    parser.add_argument("--max-unauthorized-override-total", type=int, default=1000000)
    parser.add_argument("--max-conflicting-override-total", type=int, default=1000000)
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
    summary = summarize_tool_override_audit_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_override_event_total=max(0, int(args.min_override_event_total)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_missing_reason_total=max(0, int(args.max_missing_reason_total)),
        max_missing_audit_context_total=max(0, int(args.max_missing_audit_context_total)),
        max_missing_expiry_total=max(0, int(args.max_missing_expiry_total)),
        max_unauthorized_override_total=max(0, int(args.max_unauthorized_override_total)),
        max_conflicting_override_total=max(0, int(args.max_conflicting_override_total)),
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
                "min_override_event_total": int(args.min_override_event_total),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_missing_reason_total": int(args.max_missing_reason_total),
                "max_missing_audit_context_total": int(args.max_missing_audit_context_total),
                "max_missing_expiry_total": int(args.max_missing_expiry_total),
                "max_unauthorized_override_total": int(args.max_unauthorized_override_total),
                "max_conflicting_override_total": int(args.max_conflicting_override_total),
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
    print(f"override_event_total={_safe_int(summary.get('override_event_total'), 0)}")
    print(f"override_applied_total={_safe_int(summary.get('override_applied_total'), 0)}")
    print(f"conflicting_override_total={_safe_int(summary.get('conflicting_override_total'), 0)}")
    print(f"unauthorized_override_total={_safe_int(summary.get('unauthorized_override_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
