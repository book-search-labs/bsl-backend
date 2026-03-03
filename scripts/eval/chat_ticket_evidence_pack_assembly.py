#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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


def _ticket_id(row: Mapping[str, Any]) -> str:
    return str(row.get("ticket_id") or row.get("id") or row.get("case_id") or "").strip()


def _is_ticket_created_event(row: Mapping[str, Any]) -> bool:
    event_type = str(row.get("event_type") or row.get("type") or row.get("status") or "").strip().upper()
    if event_type in {"TICKET_CREATED", "CREATE", "CREATED", "OPENED"}:
        return True
    return _safe_bool(row.get("ticket_created"), False)


def _missing_fields(row: Mapping[str, Any]) -> list[str]:
    value = row.get("missing_fields")
    if isinstance(value, list):
        fields: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                fields.append(text)
        return fields
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return []


def _has_missing_field_guidance(row: Mapping[str, Any]) -> bool:
    for key in ("missing_field_guide", "guidance", "followup_prompt", "followup_questions", "clarification_questions"):
        value = row.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
        if str(value or "").strip():
            return True
    return False


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return float(ordered[idx])


def summarize_evidence_pack_assembly(
    ticket_rows: list[Mapping[str, Any]],
    pack_rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    ticket_created_ts: dict[str, datetime | None] = {}
    for row in ticket_rows:
        ticket_id = _ticket_id(row)
        if not ticket_id:
            continue
        if not _is_ticket_created_event(row):
            continue
        if ticket_id not in ticket_created_ts:
            ticket_created_ts[ticket_id] = _event_ts(row)
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    pack_by_ticket: dict[str, dict[str, Any]] = {}
    pack_ts_by_ticket: dict[str, datetime | None] = {}
    missing_field_total = 0
    missing_field_guidance_missing_total = 0
    for row in pack_rows:
        ticket_id = _ticket_id(row)
        if not ticket_id:
            continue
        pack_by_ticket[ticket_id] = {str(k): v for k, v in row.items()}
        pack_ts_by_ticket[ticket_id] = _event_ts(row)

        missing_fields = _missing_fields(row)
        missing_field_total += len(missing_fields)
        if missing_fields and not _has_missing_field_guidance(row):
            missing_field_guidance_missing_total += 1

        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    ticket_created_total = len(ticket_created_ts)
    pack_total = len(pack_by_ticket)
    pack_assembled_total = 0
    missing_pack_total = 0
    latencies: list[float] = []

    for ticket_id, created_ts in ticket_created_ts.items():
        if ticket_id not in pack_by_ticket:
            missing_pack_total += 1
            continue
        pack_assembled_total += 1
        pack_ts = pack_ts_by_ticket.get(ticket_id)
        if created_ts is not None and pack_ts is not None:
            delta = max(0.0, (pack_ts - created_ts).total_seconds())
            latencies.append(delta)

    pack_coverage_ratio = 1.0 if ticket_created_total == 0 else float(pack_assembled_total) / float(ticket_created_total)
    p95_latency_seconds = _p95(latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": ticket_created_total,
        "ticket_created_total": ticket_created_total,
        "pack_total": pack_total,
        "pack_assembled_total": pack_assembled_total,
        "missing_pack_total": missing_pack_total,
        "pack_coverage_ratio": pack_coverage_ratio,
        "missing_field_total": missing_field_total,
        "missing_field_guidance_missing_total": missing_field_guidance_missing_total,
        "latency_sample_total": len(latencies),
        "p95_assembly_latency_seconds": p95_latency_seconds,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_pack_total: int,
    min_pack_coverage_ratio: float,
    max_missing_field_guidance_missing_total: int,
    max_p95_assembly_latency_seconds: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_pack_total = _safe_int(summary.get("missing_pack_total"), 0)
    pack_coverage_ratio = _safe_float(summary.get("pack_coverage_ratio"), 1.0)
    missing_field_guidance_missing_total = _safe_int(summary.get("missing_field_guidance_missing_total"), 0)
    p95_assembly_latency_seconds = _safe_float(summary.get("p95_assembly_latency_seconds"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket evidence assembly window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_pack_total > max(0, int(max_missing_pack_total)):
        failures.append(f"ticket evidence missing pack total exceeded: {missing_pack_total} > {int(max_missing_pack_total)}")
    if pack_coverage_ratio < max(0.0, float(min_pack_coverage_ratio)):
        failures.append(
            f"ticket evidence pack coverage ratio below threshold: {pack_coverage_ratio:.4f} < {float(min_pack_coverage_ratio):.4f}"
        )
    if missing_field_guidance_missing_total > max(0, int(max_missing_field_guidance_missing_total)):
        failures.append(
            "ticket evidence missing-field guidance missing total exceeded: "
            f"{missing_field_guidance_missing_total} > {int(max_missing_field_guidance_missing_total)}"
        )
    if p95_assembly_latency_seconds > max(0.0, float(max_p95_assembly_latency_seconds)):
        failures.append(
            "ticket evidence assembly p95 latency exceeded: "
            f"{p95_assembly_latency_seconds:.1f}s > {float(max_p95_assembly_latency_seconds):.1f}s"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket evidence assembly stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Evidence Pack Assembly")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- tickets_jsonl: {payload.get('tickets_jsonl')}")
    lines.append(f"- packs_jsonl: {payload.get('packs_jsonl')}")
    lines.append(f"- ticket_created_total: {_safe_int(summary.get('ticket_created_total'), 0)}")
    lines.append(f"- pack_assembled_total: {_safe_int(summary.get('pack_assembled_total'), 0)}")
    lines.append(f"- pack_coverage_ratio: {_safe_float(summary.get('pack_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- p95_assembly_latency_seconds: {_safe_float(summary.get('p95_assembly_latency_seconds'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat ticket evidence pack assembly quality.")
    parser.add_argument("--tickets-jsonl", default="var/chat_ticket/ticket_events.jsonl")
    parser.add_argument("--packs-jsonl", default="var/chat_ticket/evidence_packs.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_evidence_pack_assembly")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-pack-total", type=int, default=0)
    parser.add_argument("--min-pack-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--max-missing-field-guidance-missing-total", type=int, default=0)
    parser.add_argument("--max-p95-assembly-latency-seconds", type=float, default=120.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ticket_rows = _read_jsonl(
        Path(args.tickets_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    pack_rows = _read_jsonl(
        Path(args.packs_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_evidence_pack_assembly(ticket_rows, pack_rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_pack_total=max(0, int(args.max_missing_pack_total)),
        min_pack_coverage_ratio=max(0.0, float(args.min_pack_coverage_ratio)),
        max_missing_field_guidance_missing_total=max(0, int(args.max_missing_field_guidance_missing_total)),
        max_p95_assembly_latency_seconds=max(0.0, float(args.max_p95_assembly_latency_seconds)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickets_jsonl": str(args.tickets_jsonl),
        "packs_jsonl": str(args.packs_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_missing_pack_total": int(args.max_missing_pack_total),
                "min_pack_coverage_ratio": float(args.min_pack_coverage_ratio),
                "max_missing_field_guidance_missing_total": int(args.max_missing_field_guidance_missing_total),
                "max_p95_assembly_latency_seconds": float(args.max_p95_assembly_latency_seconds),
                "max_stale_minutes": float(args.max_stale_minutes),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"ticket_created_total={_safe_int(summary.get('ticket_created_total'), 0)}")
    print(f"pack_assembled_total={_safe_int(summary.get('pack_assembled_total'), 0)}")
    print(f"pack_coverage_ratio={_safe_float(summary.get('pack_coverage_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
