#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PARTIAL_FAILURE_EVENTS = {
    "PARTIAL_FAILURE",
    "PARTIAL_FAILED",
    "TOOL_PARTIAL_FAILURE",
    "WRITE_PARTIAL_FAILURE",
}
COMPENSATION_REQUIRED_EVENTS = {
    "COMPENSATION_REQUIRED",
    "NEEDS_COMPENSATION",
    "ROLLBACK_REQUIRED",
}
COMPENSATION_START_EVENTS = {
    "COMPENSATION_START",
    "COMPENSATION_STARTED",
    "ROLLBACK_START",
    "ROLLBACK_STARTED",
}
COMPENSATION_SUCCESS_EVENTS = {
    "COMPENSATION_SUCCESS",
    "COMPENSATION_SUCCEEDED",
    "ROLLBACK_COMPLETED",
    "ROLLBACK_SUCCESS",
}
COMPENSATION_FAILURE_EVENTS = {
    "COMPENSATION_FAILED",
    "ROLLBACK_FAILED",
    "COMPENSATION_ABORTED",
}
SAFE_STOP_EVENTS = {
    "SAFE_STOP",
    "SAFE_STOPPED",
    "SAFETY_HALT",
    "HALTED_SAFE",
}
ALERT_EVENTS = {
    "OPERATOR_ALERTED",
    "ALERT_SENT",
    "INCIDENT_OPENED",
    "ONCALL_PAGED",
}


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
    for key in (
        "timestamp",
        "event_time",
        "created_at",
        "updated_at",
        "resolved_at",
        "detected_at",
        "generated_at",
    ):
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


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PARTIAL_FAIL": "PARTIAL_FAILURE",
        "FAIL_PARTIAL": "PARTIAL_FAILURE",
        "COMPENSATE": "COMPENSATION_START",
        "COMPENSATE_START": "COMPENSATION_START",
        "COMPENSATE_STARTED": "COMPENSATION_STARTED",
        "COMPENSATED": "COMPENSATION_SUCCESS",
        "ROLLED_BACK": "ROLLBACK_COMPLETED",
        "ROLLBACK_DONE": "ROLLBACK_COMPLETED",
        "ALERT": "ALERT_SENT",
        "PAGE_ONCALL": "ONCALL_PAGED",
    }
    return aliases.get(text, text or "UNKNOWN")


def _event_name(row: Mapping[str, Any]) -> str:
    for key in ("event_type", "phase", "status", "step", "result"):
        token = _normalize_event(row.get(key))
        if token != "UNKNOWN":
            return token
    return "UNKNOWN"


def _tx_key(row: Mapping[str, Any]) -> str:
    tx_id = str(row.get("tx_id") or row.get("transaction_id") or "").strip()
    if tx_id:
        return tx_id
    workflow = str(row.get("workflow_id") or row.get("conversation_id") or "").strip()
    request = str(row.get("request_id") or "").strip()
    return "|".join([workflow, request]).strip("|") or "__missing__"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_tool_tx_compensation_orchestrator(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    flows: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts = _event_ts(row) or now_dt
        observed_ts = _event_ts(row)
        if observed_ts is not None and (latest_ts is None or observed_ts > latest_ts):
            latest_ts = observed_ts

        flow = flows.setdefault(
            _tx_key(row),
            {
                "partial_failure_at": None,
                "comp_required": False,
                "comp_start_at": None,
                "comp_resolved_at": None,
                "comp_succeeded": False,
                "comp_failed": False,
                "safe_stop": False,
                "alerted": False,
            },
        )

        event = _event_name(row)
        partial_failure = event in PARTIAL_FAILURE_EVENTS or _safe_bool(row.get("partial_failure_detected"), False)
        comp_required = event in COMPENSATION_REQUIRED_EVENTS or _safe_bool(row.get("compensation_required"), False)
        comp_start = event in COMPENSATION_START_EVENTS or _safe_bool(row.get("compensation_started"), False)
        comp_success = event in COMPENSATION_SUCCESS_EVENTS or _safe_bool(row.get("compensation_succeeded"), False)
        comp_failure = event in COMPENSATION_FAILURE_EVENTS or _safe_bool(row.get("compensation_failed"), False)
        safe_stop = event in SAFE_STOP_EVENTS or _safe_bool(row.get("safe_stop"), False) or _safe_bool(
            row.get("safety_halt"),
            False,
        )
        alerted = event in ALERT_EVENTS or _safe_bool(row.get("operator_alerted"), False) or _safe_bool(
            row.get("alert_sent"),
            False,
        )

        if partial_failure and flow["partial_failure_at"] is None:
            flow["partial_failure_at"] = ts
        if comp_required:
            flow["comp_required"] = True
        if comp_start and flow["comp_start_at"] is None:
            flow["comp_start_at"] = ts
        if comp_success:
            flow["comp_succeeded"] = True
            if flow["comp_resolved_at"] is None:
                flow["comp_resolved_at"] = ts
        if comp_failure:
            flow["comp_failed"] = True
            if flow["comp_resolved_at"] is None:
                flow["comp_resolved_at"] = ts
        if safe_stop:
            flow["safe_stop"] = True
        if alerted:
            flow["alerted"] = True

    compensation_required_total = 0
    compensation_started_total = 0
    compensation_succeeded_total = 0
    compensation_failed_total = 0
    compensation_missing_total = 0
    safe_stop_missing_total = 0
    operator_alert_missing_total = 0
    orphan_compensation_total = 0

    failure_to_compensation_latency_samples: list[float] = []
    compensation_resolution_latency_samples: list[float] = []

    for flow in flows.values():
        partial_failure_at = flow.get("partial_failure_at")
        comp_required = bool(flow.get("comp_required"))
        comp_start_at = flow.get("comp_start_at")
        comp_resolved_at = flow.get("comp_resolved_at")
        comp_succeeded = bool(flow.get("comp_succeeded"))
        comp_failed = bool(flow.get("comp_failed"))
        safe_stop = bool(flow.get("safe_stop"))
        alerted = bool(flow.get("alerted"))

        required = comp_required or isinstance(partial_failure_at, datetime)
        compensation_signal = isinstance(comp_start_at, datetime) or comp_succeeded or comp_failed
        first_comp_action_at = comp_start_at if isinstance(comp_start_at, datetime) else comp_resolved_at

        if required:
            compensation_required_total += 1
            if compensation_signal:
                compensation_started_total += 1
            else:
                compensation_missing_total += 1

            if comp_succeeded:
                compensation_succeeded_total += 1
            if comp_failed:
                compensation_failed_total += 1
                if not safe_stop:
                    safe_stop_missing_total += 1
                if not alerted:
                    operator_alert_missing_total += 1

            if isinstance(partial_failure_at, datetime) and isinstance(first_comp_action_at, datetime):
                failure_to_compensation_latency_samples.append(
                    max(0.0, (first_comp_action_at - partial_failure_at).total_seconds() * 1000.0)
                )
            if isinstance(partial_failure_at, datetime) and isinstance(comp_resolved_at, datetime):
                compensation_resolution_latency_samples.append(
                    max(0.0, (comp_resolved_at - partial_failure_at).total_seconds() * 1000.0)
                )
        elif compensation_signal:
            orphan_compensation_total += 1

    compensation_success_ratio = (
        1.0
        if compensation_required_total == 0
        else float(compensation_succeeded_total) / float(compensation_required_total)
    )
    compensation_resolution_ratio = (
        1.0
        if compensation_required_total == 0
        else float(compensation_succeeded_total + compensation_failed_total) / float(compensation_required_total)
    )
    p95_failure_to_compensation_latency_ms = _p95(failure_to_compensation_latency_samples)
    p95_compensation_resolution_latency_ms = _p95(compensation_resolution_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "tx_total": len(flows),
        "compensation_required_total": compensation_required_total,
        "compensation_started_total": compensation_started_total,
        "compensation_succeeded_total": compensation_succeeded_total,
        "compensation_failed_total": compensation_failed_total,
        "compensation_missing_total": compensation_missing_total,
        "safe_stop_missing_total": safe_stop_missing_total,
        "operator_alert_missing_total": operator_alert_missing_total,
        "orphan_compensation_total": orphan_compensation_total,
        "compensation_success_ratio": compensation_success_ratio,
        "compensation_resolution_ratio": compensation_resolution_ratio,
        "p95_failure_to_compensation_latency_ms": p95_failure_to_compensation_latency_ms,
        "p95_compensation_resolution_latency_ms": p95_compensation_resolution_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_compensation_required_total: int,
    min_compensation_success_ratio: float,
    min_compensation_resolution_ratio: float,
    max_compensation_failed_total: int,
    max_compensation_missing_total: int,
    max_safe_stop_missing_total: int,
    max_operator_alert_missing_total: int,
    max_orphan_compensation_total: int,
    max_p95_failure_to_compensation_latency_ms: float,
    max_p95_compensation_resolution_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    compensation_required_total = _safe_int(summary.get("compensation_required_total"), 0)
    compensation_success_ratio = _safe_float(summary.get("compensation_success_ratio"), 0.0)
    compensation_resolution_ratio = _safe_float(summary.get("compensation_resolution_ratio"), 0.0)
    compensation_failed_total = _safe_int(summary.get("compensation_failed_total"), 0)
    compensation_missing_total = _safe_int(summary.get("compensation_missing_total"), 0)
    safe_stop_missing_total = _safe_int(summary.get("safe_stop_missing_total"), 0)
    operator_alert_missing_total = _safe_int(summary.get("operator_alert_missing_total"), 0)
    orphan_compensation_total = _safe_int(summary.get("orphan_compensation_total"), 0)
    p95_failure_to_compensation_latency_ms = _safe_float(summary.get("p95_failure_to_compensation_latency_ms"), 0.0)
    p95_compensation_resolution_latency_ms = _safe_float(summary.get("p95_compensation_resolution_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat tool tx compensation window too small: {window_size} < {int(min_window)}")
    if compensation_required_total < max(0, int(min_compensation_required_total)):
        failures.append(
            "chat tool tx compensation required total too small: "
            f"{compensation_required_total} < {int(min_compensation_required_total)}"
        )
    if window_size == 0:
        return failures

    if compensation_success_ratio < max(0.0, float(min_compensation_success_ratio)):
        failures.append(
            "chat tool tx compensation success ratio below minimum: "
            f"{compensation_success_ratio:.4f} < {float(min_compensation_success_ratio):.4f}"
        )
    if compensation_resolution_ratio < max(0.0, float(min_compensation_resolution_ratio)):
        failures.append(
            "chat tool tx compensation resolution ratio below minimum: "
            f"{compensation_resolution_ratio:.4f} < {float(min_compensation_resolution_ratio):.4f}"
        )
    if compensation_failed_total > max(0, int(max_compensation_failed_total)):
        failures.append(
            f"chat tool tx compensation failed total exceeded: {compensation_failed_total} > {int(max_compensation_failed_total)}"
        )
    if compensation_missing_total > max(0, int(max_compensation_missing_total)):
        failures.append(
            f"chat tool tx compensation missing total exceeded: {compensation_missing_total} > {int(max_compensation_missing_total)}"
        )
    if safe_stop_missing_total > max(0, int(max_safe_stop_missing_total)):
        failures.append(
            f"chat tool tx safe-stop missing total exceeded: {safe_stop_missing_total} > {int(max_safe_stop_missing_total)}"
        )
    if operator_alert_missing_total > max(0, int(max_operator_alert_missing_total)):
        failures.append(
            "chat tool tx operator-alert missing total exceeded: "
            f"{operator_alert_missing_total} > {int(max_operator_alert_missing_total)}"
        )
    if orphan_compensation_total > max(0, int(max_orphan_compensation_total)):
        failures.append(
            f"chat tool tx orphan compensation total exceeded: {orphan_compensation_total} > {int(max_orphan_compensation_total)}"
        )
    if p95_failure_to_compensation_latency_ms > max(0.0, float(max_p95_failure_to_compensation_latency_ms)):
        failures.append(
            "chat tool tx p95 failure->compensation latency exceeded: "
            f"{p95_failure_to_compensation_latency_ms:.2f}ms > {float(max_p95_failure_to_compensation_latency_ms):.2f}ms"
        )
    if p95_compensation_resolution_latency_ms > max(0.0, float(max_p95_compensation_resolution_latency_ms)):
        failures.append(
            "chat tool tx p95 compensation resolution latency exceeded: "
            f"{p95_compensation_resolution_latency_ms:.2f}ms > {float(max_p95_compensation_resolution_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat tool tx compensation stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Transaction Compensation Orchestrator")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- compensation_required_total: {_safe_int(summary.get('compensation_required_total'), 0)}")
    lines.append(f"- compensation_succeeded_total: {_safe_int(summary.get('compensation_succeeded_total'), 0)}")
    lines.append(f"- compensation_failed_total: {_safe_int(summary.get('compensation_failed_total'), 0)}")
    lines.append(f"- safe_stop_missing_total: {_safe_int(summary.get('safe_stop_missing_total'), 0)}")
    lines.append(f"- operator_alert_missing_total: {_safe_int(summary.get('operator_alert_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool transaction compensation orchestration quality.")
    parser.add_argument("--events-jsonl", default="var/chat_tool_tx/tx_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_tx_compensation_orchestrator")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-compensation-required-total", type=int, default=0)
    parser.add_argument("--min-compensation-success-ratio", type=float, default=0.0)
    parser.add_argument("--min-compensation-resolution-ratio", type=float, default=0.0)
    parser.add_argument("--max-compensation-failed-total", type=int, default=0)
    parser.add_argument("--max-compensation-missing-total", type=int, default=0)
    parser.add_argument("--max-safe-stop-missing-total", type=int, default=0)
    parser.add_argument("--max-operator-alert-missing-total", type=int, default=0)
    parser.add_argument("--max-orphan-compensation-total", type=int, default=0)
    parser.add_argument("--max-p95-failure-to-compensation-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-p95-compensation-resolution-latency-ms", type=float, default=1000000.0)
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
    summary = summarize_tool_tx_compensation_orchestrator(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_compensation_required_total=max(0, int(args.min_compensation_required_total)),
        min_compensation_success_ratio=max(0.0, float(args.min_compensation_success_ratio)),
        min_compensation_resolution_ratio=max(0.0, float(args.min_compensation_resolution_ratio)),
        max_compensation_failed_total=max(0, int(args.max_compensation_failed_total)),
        max_compensation_missing_total=max(0, int(args.max_compensation_missing_total)),
        max_safe_stop_missing_total=max(0, int(args.max_safe_stop_missing_total)),
        max_operator_alert_missing_total=max(0, int(args.max_operator_alert_missing_total)),
        max_orphan_compensation_total=max(0, int(args.max_orphan_compensation_total)),
        max_p95_failure_to_compensation_latency_ms=max(0.0, float(args.max_p95_failure_to_compensation_latency_ms)),
        max_p95_compensation_resolution_latency_ms=max(0.0, float(args.max_p95_compensation_resolution_latency_ms)),
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
                "min_compensation_required_total": int(args.min_compensation_required_total),
                "min_compensation_success_ratio": float(args.min_compensation_success_ratio),
                "min_compensation_resolution_ratio": float(args.min_compensation_resolution_ratio),
                "max_compensation_failed_total": int(args.max_compensation_failed_total),
                "max_compensation_missing_total": int(args.max_compensation_missing_total),
                "max_safe_stop_missing_total": int(args.max_safe_stop_missing_total),
                "max_operator_alert_missing_total": int(args.max_operator_alert_missing_total),
                "max_orphan_compensation_total": int(args.max_orphan_compensation_total),
                "max_p95_failure_to_compensation_latency_ms": float(args.max_p95_failure_to_compensation_latency_ms),
                "max_p95_compensation_resolution_latency_ms": float(args.max_p95_compensation_resolution_latency_ms),
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
    print(f"compensation_required_total={_safe_int(summary.get('compensation_required_total'), 0)}")
    print(f"compensation_failed_total={_safe_int(summary.get('compensation_failed_total'), 0)}")
    print(f"safe_stop_missing_total={_safe_int(summary.get('safe_stop_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
