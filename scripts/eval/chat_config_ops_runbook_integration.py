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


def _event_ts(row: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


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


def summarize_ops_integration(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    alert_sent_total = 0
    missing_runbook_total = 0
    missing_recommended_action_total = 0
    missing_bundle_version_total = 0
    missing_impacted_services_total = 0
    payload_complete_total = 0
    latest_ts: datetime | None = None
    by_incident: dict[str, int] = {}

    for row in events:
        alert_sent = _safe_bool(row.get("alert_sent"), False) or _safe_bool(row.get("notified"), False)
        runbook = str(row.get("runbook_link") or row.get("playbook_link") or "").strip()
        action = str(row.get("recommended_action") or row.get("next_action") or "").strip()
        bundle_version = str(row.get("bundle_version") or row.get("bundle_id") or row.get("config_version") or "").strip()
        impacted_services = row.get("impacted_services")
        incident_type = str(row.get("incident_type") or row.get("failure_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        by_incident[incident_type] = by_incident.get(incident_type, 0) + 1

        if alert_sent:
            alert_sent_total += 1
        if not runbook:
            missing_runbook_total += 1
        if not action:
            missing_recommended_action_total += 1
        if not bundle_version:
            missing_bundle_version_total += 1

        impacted_count = 0
        if isinstance(impacted_services, list):
            impacted_count = sum(1 for item in impacted_services if str(item or "").strip())
        elif isinstance(impacted_services, str):
            impacted_count = 1 if impacted_services.strip() else 0
        if impacted_count <= 0:
            missing_impacted_services_total += 1

        if runbook and action and bundle_version and impacted_count > 0:
            payload_complete_total += 1

    window_size = len(events)
    alert_ratio = 0.0 if window_size == 0 else float(alert_sent_total) / float(window_size)
    payload_complete_ratio = 0.0 if window_size == 0 else float(payload_complete_total) / float(window_size)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": window_size,
        "alert_sent_total": alert_sent_total,
        "alert_ratio": alert_ratio,
        "payload_complete_total": payload_complete_total,
        "payload_complete_ratio": payload_complete_ratio,
        "missing_runbook_total": missing_runbook_total,
        "missing_recommended_action_total": missing_recommended_action_total,
        "missing_bundle_version_total": missing_bundle_version_total,
        "missing_impacted_services_total": missing_impacted_services_total,
        "incidents": [{"incident_type": key, "count": value} for key, value in sorted(by_incident.items(), key=lambda item: item[1], reverse=True)],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_payload_complete_ratio: float,
    max_missing_runbook_total: int,
    max_missing_recommended_action_total: int,
    max_missing_bundle_version_total: int,
    max_missing_impacted_services_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    payload_complete_ratio = _safe_float(summary.get("payload_complete_ratio"), 0.0)
    missing_runbook_total = _safe_int(summary.get("missing_runbook_total"), 0)
    missing_recommended_action_total = _safe_int(summary.get("missing_recommended_action_total"), 0)
    missing_bundle_version_total = _safe_int(summary.get("missing_bundle_version_total"), 0)
    missing_impacted_services_total = _safe_int(summary.get("missing_impacted_services_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ops integration window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if payload_complete_ratio < max(0.0, float(min_payload_complete_ratio)):
        failures.append(
            f"ops payload completeness below threshold: {payload_complete_ratio:.4f} < {float(min_payload_complete_ratio):.4f}"
        )
    if missing_runbook_total > max(0, int(max_missing_runbook_total)):
        failures.append(f"missing runbook total exceeded: {missing_runbook_total} > {int(max_missing_runbook_total)}")
    if missing_recommended_action_total > max(0, int(max_missing_recommended_action_total)):
        failures.append(
            f"missing recommended action total exceeded: {missing_recommended_action_total} > {int(max_missing_recommended_action_total)}"
        )
    if missing_bundle_version_total > max(0, int(max_missing_bundle_version_total)):
        failures.append(
            f"missing bundle version total exceeded: {missing_bundle_version_total} > {int(max_missing_bundle_version_total)}"
        )
    if missing_impacted_services_total > max(0, int(max_missing_impacted_services_total)):
        failures.append(
            f"missing impacted services total exceeded: {missing_impacted_services_total} > {int(max_missing_impacted_services_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ops integration events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Config Ops Runbook Integration")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- payload_complete_ratio: {_safe_float(summary.get('payload_complete_ratio'), 0.0):.4f}")
    lines.append(f"- missing_runbook_total: {_safe_int(summary.get('missing_runbook_total'), 0)}")
    lines.append(f"- missing_recommended_action_total: {_safe_int(summary.get('missing_recommended_action_total'), 0)}")
    lines.append(f"- missing_bundle_version_total: {_safe_int(summary.get('missing_bundle_version_total'), 0)}")
    lines.append(f"- missing_impacted_services_total: {_safe_int(summary.get('missing_impacted_services_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate config deployment ops-runbook integration completeness.")
    parser.add_argument("--events-jsonl", default="var/chat_control/config_ops_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_config_ops_runbook_integration")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-payload-complete-ratio", type=float, default=0.95)
    parser.add_argument("--max-missing-runbook-total", type=int, default=0)
    parser.add_argument("--max-missing-recommended-action-total", type=int, default=0)
    parser.add_argument("--max-missing-bundle-version-total", type=int, default=0)
    parser.add_argument("--max-missing-impacted-services-total", type=int, default=0)
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
    summary = summarize_ops_integration(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_payload_complete_ratio=max(0.0, float(args.min_payload_complete_ratio)),
        max_missing_runbook_total=max(0, int(args.max_missing_runbook_total)),
        max_missing_recommended_action_total=max(0, int(args.max_missing_recommended_action_total)),
        max_missing_bundle_version_total=max(0, int(args.max_missing_bundle_version_total)),
        max_missing_impacted_services_total=max(0, int(args.max_missing_impacted_services_total)),
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
                "min_payload_complete_ratio": float(args.min_payload_complete_ratio),
                "max_missing_runbook_total": int(args.max_missing_runbook_total),
                "max_missing_recommended_action_total": int(args.max_missing_recommended_action_total),
                "max_missing_bundle_version_total": int(args.max_missing_bundle_version_total),
                "max_missing_impacted_services_total": int(args.max_missing_impacted_services_total),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"payload_complete_ratio={_safe_float(summary.get('payload_complete_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
