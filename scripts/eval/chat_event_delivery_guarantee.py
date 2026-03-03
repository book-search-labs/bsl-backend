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


def _stream_id(row: Mapping[str, Any]) -> str:
    for key in ("stream_id", "session_id", "connection_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "global"


def _event_seq(row: Mapping[str, Any]) -> int | None:
    for key in ("event_seq", "seq", "sequence", "turn_seq"):
        raw = row.get(key)
        if raw is None:
            continue
        return _safe_int(raw, 0)
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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def summarize_delivery(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    delivered_total = 0
    order_violation_total = 0
    duplicate_total = 0
    ack_missing_total = 0
    redelivery_total = 0
    ttl_drop_total = 0
    sync_gap_total = 0
    max_sync_gap = 0

    latest_ts: datetime | None = None
    by_reason: dict[str, int] = {}
    stream_last_seq: dict[str, int] = {}

    for row in events:
        stream_id = _stream_id(row)
        seq = _event_seq(row)
        expected_seq = row.get("expected_seq")
        delivered = _safe_bool(row.get("delivered"), True)
        acked = _safe_bool(row.get("acked"), True)
        duplicate = _safe_bool(row.get("duplicate"), False)
        redelivery_count = max(0, _safe_int(row.get("redelivery_count"), 0))
        sync_gap_events = max(0, _safe_int(row.get("sync_gap_events"), 0))
        reason = str(row.get("reason_code") or row.get("reason") or "NONE").strip().upper()
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if delivered:
            delivered_total += 1

        if duplicate:
            duplicate_total += 1

        if not acked:
            ack_missing_total += 1

        redelivery_total += redelivery_count

        if reason in {"TTL_EXPIRED", "ACK_TIMEOUT", "DELIVERY_TTL_EXPIRED"}:
            ttl_drop_total += 1

        sync_gap_total += sync_gap_events
        if sync_gap_events > max_sync_gap:
            max_sync_gap = sync_gap_events

        if reason:
            by_reason[reason] = by_reason.get(reason, 0) + 1

        if seq is not None:
            if expected_seq is not None and _safe_int(expected_seq, seq) != seq:
                order_violation_total += 1
            last_seq = stream_last_seq.get(stream_id)
            if last_seq is not None and seq <= last_seq:
                order_violation_total += 1
            stream_last_seq[stream_id] = max(seq, last_seq or seq)

    window_size = len(events)
    delivery_success_ratio = 1.0 if window_size == 0 else float(delivered_total) / float(window_size)
    duplicate_ratio = 0.0 if window_size == 0 else float(duplicate_total) / float(window_size)
    ack_missing_ratio = 0.0 if window_size == 0 else float(ack_missing_total) / float(window_size)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(by_reason.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "window_size": window_size,
        "stream_total": len(stream_last_seq),
        "delivered_total": delivered_total,
        "delivery_success_ratio": delivery_success_ratio,
        "order_violation_total": order_violation_total,
        "duplicate_total": duplicate_total,
        "duplicate_ratio": duplicate_ratio,
        "ack_missing_total": ack_missing_total,
        "ack_missing_ratio": ack_missing_ratio,
        "redelivery_total": redelivery_total,
        "ttl_drop_total": ttl_drop_total,
        "sync_gap_total": sync_gap_total,
        "max_sync_gap": max_sync_gap,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
        "top_reasons": reasons,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_delivery_success_ratio: float,
    max_order_violation_total: int,
    max_duplicate_ratio: float,
    max_ack_missing_ratio: float,
    max_sync_gap: int,
    max_ttl_drop_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    delivery_success_ratio = _safe_float(summary.get("delivery_success_ratio"), 1.0)
    order_violation_total = _safe_int(summary.get("order_violation_total"), 0)
    duplicate_ratio = _safe_float(summary.get("duplicate_ratio"), 0.0)
    ack_missing_ratio = _safe_float(summary.get("ack_missing_ratio"), 0.0)
    max_sync_gap_seen = _safe_int(summary.get("max_sync_gap"), 0)
    ttl_drop_total = _safe_int(summary.get("ttl_drop_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"event delivery window too small: {window_size} < {int(min_window)}")
    if delivery_success_ratio < max(0.0, float(min_delivery_success_ratio)):
        failures.append(
            f"delivery success ratio below threshold: {delivery_success_ratio:.4f} < {float(min_delivery_success_ratio):.4f}"
        )
    if order_violation_total > max(0, int(max_order_violation_total)):
        failures.append(
            f"ordered delivery violations exceeded: {order_violation_total} > {int(max_order_violation_total)}"
        )
    if duplicate_ratio > max(0.0, float(max_duplicate_ratio)):
        failures.append(f"duplicate ratio exceeded: {duplicate_ratio:.4f} > {float(max_duplicate_ratio):.4f}")
    if ack_missing_ratio > max(0.0, float(max_ack_missing_ratio)):
        failures.append(
            f"ack missing ratio exceeded: {ack_missing_ratio:.4f} > {float(max_ack_missing_ratio):.4f}"
        )
    if max_sync_gap_seen > max(0, int(max_sync_gap)):
        failures.append(f"sync gap exceeded: {max_sync_gap_seen} > {int(max_sync_gap)}")
    if ttl_drop_total > max(0, int(max_ttl_drop_total)):
        failures.append(f"ttl drop events exceeded: {ttl_drop_total} > {int(max_ttl_drop_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"event delivery logs stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")

    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_delivery_success_ratio_drop: float,
    max_order_violation_total_increase: int,
    max_duplicate_ratio_increase: float,
    max_ack_missing_ratio_increase: float,
    max_ttl_drop_total_increase: int,
) -> list[str]:
    failures: list[str] = []

    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_delivery_success_ratio = _safe_float(base_summary.get("delivery_success_ratio"), 1.0)
    cur_delivery_success_ratio = _safe_float(current_summary.get("delivery_success_ratio"), 1.0)
    delivery_success_ratio_drop = max(0.0, base_delivery_success_ratio - cur_delivery_success_ratio)
    if delivery_success_ratio_drop > max(0.0, float(max_delivery_success_ratio_drop)):
        failures.append(
            "delivery success regression: "
            f"baseline={base_delivery_success_ratio:.6f}, current={cur_delivery_success_ratio:.6f}, "
            f"allowed_drop={float(max_delivery_success_ratio_drop):.6f}"
        )

    base_order_violation_total = _safe_int(base_summary.get("order_violation_total"), 0)
    cur_order_violation_total = _safe_int(current_summary.get("order_violation_total"), 0)
    order_violation_total_increase = max(0, cur_order_violation_total - base_order_violation_total)
    if order_violation_total_increase > max(0, int(max_order_violation_total_increase)):
        failures.append(
            "order violation regression: "
            f"baseline={base_order_violation_total}, current={cur_order_violation_total}, "
            f"allowed_increase={max(0, int(max_order_violation_total_increase))}"
        )

    base_duplicate_ratio = _safe_float(base_summary.get("duplicate_ratio"), 0.0)
    cur_duplicate_ratio = _safe_float(current_summary.get("duplicate_ratio"), 0.0)
    duplicate_ratio_increase = max(0.0, cur_duplicate_ratio - base_duplicate_ratio)
    if duplicate_ratio_increase > max(0.0, float(max_duplicate_ratio_increase)):
        failures.append(
            "duplicate ratio regression: "
            f"baseline={base_duplicate_ratio:.6f}, current={cur_duplicate_ratio:.6f}, "
            f"allowed_increase={float(max_duplicate_ratio_increase):.6f}"
        )

    base_ack_missing_ratio = _safe_float(base_summary.get("ack_missing_ratio"), 0.0)
    cur_ack_missing_ratio = _safe_float(current_summary.get("ack_missing_ratio"), 0.0)
    ack_missing_ratio_increase = max(0.0, cur_ack_missing_ratio - base_ack_missing_ratio)
    if ack_missing_ratio_increase > max(0.0, float(max_ack_missing_ratio_increase)):
        failures.append(
            "ack missing ratio regression: "
            f"baseline={base_ack_missing_ratio:.6f}, current={cur_ack_missing_ratio:.6f}, "
            f"allowed_increase={float(max_ack_missing_ratio_increase):.6f}"
        )

    base_ttl_drop_total = _safe_int(base_summary.get("ttl_drop_total"), 0)
    cur_ttl_drop_total = _safe_int(current_summary.get("ttl_drop_total"), 0)
    ttl_drop_total_increase = max(0, cur_ttl_drop_total - base_ttl_drop_total)
    if ttl_drop_total_increase > max(0, int(max_ttl_drop_total_increase)):
        failures.append(
            "ttl drop regression: "
            f"baseline={base_ttl_drop_total}, current={cur_ttl_drop_total}, "
            f"allowed_increase={max(0, int(max_ttl_drop_total_increase))}"
        )

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Event Delivery Guarantee")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- delivery_success_ratio: {_safe_float(summary.get('delivery_success_ratio'), 0.0):.4f}")
    lines.append(f"- order_violation_total: {_safe_int(summary.get('order_violation_total'), 0)}")
    lines.append(f"- duplicate_ratio: {_safe_float(summary.get('duplicate_ratio'), 0.0):.4f}")
    lines.append(f"- ack_missing_ratio: {_safe_float(summary.get('ack_missing_ratio'), 0.0):.4f}")
    lines.append(f"- max_sync_gap: {_safe_int(summary.get('max_sync_gap'), 0)}")
    lines.append(f"- ttl_drop_total: {_safe_int(summary.get('ttl_drop_total'), 0)}")

    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ordered event delivery/redelivery/ack guarantees for chat session gateway.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/event_delivery_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_event_delivery_guarantee")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-delivery-success-ratio", type=float, default=0.99)
    parser.add_argument("--max-order-violation-total", type=int, default=0)
    parser.add_argument("--max-duplicate-ratio", type=float, default=0.01)
    parser.add_argument("--max-ack-missing-ratio", type=float, default=0.02)
    parser.add_argument("--max-sync-gap", type=int, default=5)
    parser.add_argument("--max-ttl-drop-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-delivery-success-ratio-drop", type=float, default=0.01)
    parser.add_argument("--max-order-violation-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-ack-missing-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-ttl-drop-total-increase", type=int, default=0)
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

    summary = summarize_delivery(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_delivery_success_ratio=max(0.0, float(args.min_delivery_success_ratio)),
        max_order_violation_total=max(0, int(args.max_order_violation_total)),
        max_duplicate_ratio=max(0.0, float(args.max_duplicate_ratio)),
        max_ack_missing_ratio=max(0.0, float(args.max_ack_missing_ratio)),
        max_sync_gap=max(0, int(args.max_sync_gap)),
        max_ttl_drop_total=max(0, int(args.max_ttl_drop_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_delivery_success_ratio_drop=max(0.0, float(args.max_delivery_success_ratio_drop)),
            max_order_violation_total_increase=max(0, int(args.max_order_violation_total_increase)),
            max_duplicate_ratio_increase=max(0.0, float(args.max_duplicate_ratio_increase)),
            max_ack_missing_ratio_increase=max(0.0, float(args.max_ack_missing_ratio_increase)),
            max_ttl_drop_total_increase=max(0, int(args.max_ttl_drop_total_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_delivery_success_ratio": float(args.min_delivery_success_ratio),
                "max_order_violation_total": int(args.max_order_violation_total),
                "max_duplicate_ratio": float(args.max_duplicate_ratio),
                "max_ack_missing_ratio": float(args.max_ack_missing_ratio),
                "max_sync_gap": int(args.max_sync_gap),
                "max_ttl_drop_total": int(args.max_ttl_drop_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_delivery_success_ratio_drop": float(args.max_delivery_success_ratio_drop),
                "max_order_violation_total_increase": int(args.max_order_violation_total_increase),
                "max_duplicate_ratio_increase": float(args.max_duplicate_ratio_increase),
                "max_ack_missing_ratio_increase": float(args.max_ack_missing_ratio_increase),
                "max_ttl_drop_total_increase": int(args.max_ttl_drop_total_increase),
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
    print(f"delivery_success_ratio={_safe_float(summary.get('delivery_success_ratio'), 0.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and not payload["gate"]["pass"]:
        for failure in failures:
            print(f"[gate-failure] {failure}")
        for failure in baseline_failures:
            print(f"[baseline-failure] {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
