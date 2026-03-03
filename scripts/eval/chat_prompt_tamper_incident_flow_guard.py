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


def _tamper_suspected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("tamper_suspected"), False):
        return True
    event_type = str(row.get("event_type") or "").strip().lower()
    return event_type in {"tamper_suspected", "prompt_tamper_detected", "integrity_tamper_detected"}


def _alert_emitted(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("alert_emitted"), False):
        return True
    return bool(str(row.get("alert_id") or row.get("alert_event_id") or "").strip())


def _incident_created(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("incident_created"), False):
        return True
    return bool(str(row.get("incident_id") or row.get("ticket_id") or "").strip())


def _triage_started(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("triage_started"), False):
        return True
    return bool(str(row.get("triage_id") or "").strip())


def _quarantine_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("quarantine_applied"), False):
        return True
    return _safe_bool(row.get("auto_isolation_applied"), False)


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("incident_reason_code") or "").strip())


def _alert_latency_sec(row: Mapping[str, Any]) -> float:
    explicit = row.get("alert_latency_sec")
    if explicit is not None:
        return max(0.0, _safe_float(explicit, 0.0))
    detected_at = _parse_ts(row.get("tamper_detected_at"))
    alert_at = _parse_ts(row.get("alert_emitted_at"))
    if detected_at is None or alert_at is None:
        return 0.0
    return max(0.0, (alert_at - detected_at).total_seconds())


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_prompt_tamper_incident_flow_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    tamper_event_total = 0
    alert_emitted_total = 0
    incident_created_total = 0
    triage_started_total = 0
    quarantine_applied_total = 0
    uncontained_tamper_total = 0
    reason_code_missing_total = 0
    alert_latency_samples: list[float] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _tamper_suspected(row):
            continue
        tamper_event_total += 1

        alert_emitted = _alert_emitted(row)
        incident_created = _incident_created(row)
        triage_started = _triage_started(row)
        quarantine_applied = _quarantine_applied(row)
        reason_present = _reason_present(row)

        if alert_emitted:
            alert_emitted_total += 1
            alert_latency_samples.append(_alert_latency_sec(row))
        if incident_created:
            incident_created_total += 1
        if triage_started:
            triage_started_total += 1
        if quarantine_applied:
            quarantine_applied_total += 1
        else:
            uncontained_tamper_total += 1
        if not reason_present:
            reason_code_missing_total += 1

    alert_coverage_ratio = 1.0 if tamper_event_total == 0 else float(alert_emitted_total) / float(tamper_event_total)
    incident_coverage_ratio = (
        1.0 if tamper_event_total == 0 else float(incident_created_total) / float(tamper_event_total)
    )
    quarantine_coverage_ratio = (
        1.0 if tamper_event_total == 0 else float(quarantine_applied_total) / float(tamper_event_total)
    )
    alert_latency_p95_sec = _p95(alert_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "tamper_event_total": tamper_event_total,
        "alert_emitted_total": alert_emitted_total,
        "alert_coverage_ratio": alert_coverage_ratio,
        "incident_created_total": incident_created_total,
        "incident_coverage_ratio": incident_coverage_ratio,
        "triage_started_total": triage_started_total,
        "quarantine_applied_total": quarantine_applied_total,
        "quarantine_coverage_ratio": quarantine_coverage_ratio,
        "uncontained_tamper_total": uncontained_tamper_total,
        "reason_code_missing_total": reason_code_missing_total,
        "alert_latency_p95_sec": alert_latency_p95_sec,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_tamper_event_total: int,
    min_alert_coverage_ratio: float,
    min_incident_coverage_ratio: float,
    min_quarantine_coverage_ratio: float,
    max_alert_latency_p95_sec: float,
    max_uncontained_tamper_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    tamper_event_total = _safe_int(summary.get("tamper_event_total"), 0)
    alert_coverage_ratio = _safe_float(summary.get("alert_coverage_ratio"), 0.0)
    incident_coverage_ratio = _safe_float(summary.get("incident_coverage_ratio"), 0.0)
    quarantine_coverage_ratio = _safe_float(summary.get("quarantine_coverage_ratio"), 0.0)
    alert_latency_p95_sec = _safe_float(summary.get("alert_latency_p95_sec"), 0.0)
    uncontained_tamper_total = _safe_int(summary.get("uncontained_tamper_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat prompt tamper flow window too small: {window_size} < {int(min_window)}")
    if tamper_event_total < max(0, int(min_tamper_event_total)):
        failures.append(
            f"chat prompt tamper event total too small: {tamper_event_total} < {int(min_tamper_event_total)}"
        )
    if window_size == 0:
        return failures

    if alert_coverage_ratio < max(0.0, float(min_alert_coverage_ratio)):
        failures.append(
            f"chat prompt tamper alert coverage ratio below minimum: {alert_coverage_ratio:.4f} < {float(min_alert_coverage_ratio):.4f}"
        )
    if incident_coverage_ratio < max(0.0, float(min_incident_coverage_ratio)):
        failures.append(
            f"chat prompt tamper incident coverage ratio below minimum: {incident_coverage_ratio:.4f} < {float(min_incident_coverage_ratio):.4f}"
        )
    if quarantine_coverage_ratio < max(0.0, float(min_quarantine_coverage_ratio)):
        failures.append(
            f"chat prompt tamper quarantine coverage ratio below minimum: {quarantine_coverage_ratio:.4f} < {float(min_quarantine_coverage_ratio):.4f}"
        )
    if alert_latency_p95_sec > max(0.0, float(max_alert_latency_p95_sec)):
        failures.append(
            f"chat prompt tamper alert latency p95 exceeded: {alert_latency_p95_sec:.2f}s > {float(max_alert_latency_p95_sec):.2f}s"
        )
    if uncontained_tamper_total > max(0, int(max_uncontained_tamper_total)):
        failures.append(
            f"chat prompt tamper uncontained total exceeded: {uncontained_tamper_total} > {int(max_uncontained_tamper_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat prompt tamper reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat prompt tamper flow stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Prompt Tamper Incident Flow Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- tamper_event_total: {_safe_int(summary.get('tamper_event_total'), 0)}")
    lines.append(f"- alert_coverage_ratio: {_safe_float(summary.get('alert_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- incident_coverage_ratio: {_safe_float(summary.get('incident_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- quarantine_coverage_ratio: {_safe_float(summary.get('quarantine_coverage_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate tamper incident flow for prompt supply chain.")
    parser.add_argument("--events-jsonl", default="var/chat_prompt_supply/tamper_incident_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_prompt_tamper_incident_flow_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-tamper-event-total", type=int, default=0)
    parser.add_argument("--min-alert-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-incident-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-quarantine-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-alert-latency-p95-sec", type=float, default=1000000.0)
    parser.add_argument("--max-uncontained-tamper-total", type=int, default=1000000)
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
    summary = summarize_prompt_tamper_incident_flow_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_tamper_event_total=max(0, int(args.min_tamper_event_total)),
        min_alert_coverage_ratio=max(0.0, float(args.min_alert_coverage_ratio)),
        min_incident_coverage_ratio=max(0.0, float(args.min_incident_coverage_ratio)),
        min_quarantine_coverage_ratio=max(0.0, float(args.min_quarantine_coverage_ratio)),
        max_alert_latency_p95_sec=max(0.0, float(args.max_alert_latency_p95_sec)),
        max_uncontained_tamper_total=max(0, int(args.max_uncontained_tamper_total)),
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
                "min_tamper_event_total": int(args.min_tamper_event_total),
                "min_alert_coverage_ratio": float(args.min_alert_coverage_ratio),
                "min_incident_coverage_ratio": float(args.min_incident_coverage_ratio),
                "min_quarantine_coverage_ratio": float(args.min_quarantine_coverage_ratio),
                "max_alert_latency_p95_sec": float(args.max_alert_latency_p95_sec),
                "max_uncontained_tamper_total": int(args.max_uncontained_tamper_total),
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
    print(f"tamper_event_total={_safe_int(summary.get('tamper_event_total'), 0)}")
    print(f"alert_coverage_ratio={_safe_float(summary.get('alert_coverage_ratio'), 0.0):.4f}")
    print(f"quarantine_coverage_ratio={_safe_float(summary.get('quarantine_coverage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
