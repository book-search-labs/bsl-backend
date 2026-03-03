#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


BAND_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
AUTO_ACTIONS = {"AUTO_REPLY", "AUTO", "DIRECT_ANSWER", "ANSWER", "RESPOND"}
APPROVAL_ACTIONS = {"APPROVAL_QUEUE", "REQUIRE_APPROVAL", "HUMAN_APPROVAL", "REVIEW_QUEUE", "ESCALATE", "HANDOFF"}
QUEUE_REQUIRED_ACTIONS = {"APPROVAL_QUEUE", "REQUIRE_APPROVAL", "HUMAN_APPROVAL", "REVIEW_QUEUE", "ESCALATE", "HANDOFF"}


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_band(value: Any) -> str:
    token = _normalize_token(value)
    if token in BAND_ORDER:
        return token
    if token in {"0", "RISK_0"}:
        return "R0"
    if token in {"1", "RISK_1"}:
        return "R1"
    if token in {"2", "RISK_2"}:
        return "R2"
    if token in {"3", "RISK_3"}:
        return "R3"
    return ""


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


def _action(row: Mapping[str, Any]) -> str:
    return _normalize_token(
        row.get("approval_action") or row.get("next_action") or row.get("route_result") or row.get("response_mode")
    )


def _queue_id(row: Mapping[str, Any]) -> str:
    return str(row.get("approval_queue_id") or row.get("queue_id") or row.get("ticket_id") or "").strip()


def summarize_answer_tiered_approval_flow_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    missing_band_total = 0
    high_risk_total = 0
    approval_routed_total = 0
    unsafe_auto_high_risk_total = 0
    r3_auto_total = 0
    approval_queue_missing_total = 0
    low_risk_total = 0
    low_risk_auto_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        band = _normalize_band(row.get("risk_band") or row.get("assigned_band"))
        action = _action(row)

        if not band:
            missing_band_total += 1
            continue

        if BAND_ORDER[band] >= BAND_ORDER["R2"]:
            high_risk_total += 1
            if action in APPROVAL_ACTIONS:
                approval_routed_total += 1
            if action in AUTO_ACTIONS:
                unsafe_auto_high_risk_total += 1
            if band == "R3" and action in AUTO_ACTIONS:
                r3_auto_total += 1
            if action in QUEUE_REQUIRED_ACTIONS and not _queue_id(row):
                approval_queue_missing_total += 1
        else:
            low_risk_total += 1
            if action in AUTO_ACTIONS:
                low_risk_auto_total += 1

    high_risk_approval_coverage_ratio = (
        1.0 if high_risk_total == 0 else float(approval_routed_total) / float(high_risk_total)
    )
    low_risk_auto_ratio = 1.0 if low_risk_total == 0 else float(low_risk_auto_total) / float(low_risk_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "missing_band_total": missing_band_total,
        "high_risk_total": high_risk_total,
        "approval_routed_total": approval_routed_total,
        "high_risk_approval_coverage_ratio": high_risk_approval_coverage_ratio,
        "unsafe_auto_high_risk_total": unsafe_auto_high_risk_total,
        "r3_auto_total": r3_auto_total,
        "approval_queue_missing_total": approval_queue_missing_total,
        "low_risk_total": low_risk_total,
        "low_risk_auto_total": low_risk_auto_total,
        "low_risk_auto_ratio": low_risk_auto_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_high_risk_approval_coverage_ratio: float,
    min_low_risk_auto_ratio: float,
    max_missing_band_total: int,
    max_unsafe_auto_high_risk_total: int,
    max_r3_auto_total: int,
    max_approval_queue_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    high_risk_approval_coverage_ratio = _safe_float(summary.get("high_risk_approval_coverage_ratio"), 0.0)
    low_risk_auto_ratio = _safe_float(summary.get("low_risk_auto_ratio"), 0.0)
    missing_band_total = _safe_int(summary.get("missing_band_total"), 0)
    unsafe_auto_high_risk_total = _safe_int(summary.get("unsafe_auto_high_risk_total"), 0)
    r3_auto_total = _safe_int(summary.get("r3_auto_total"), 0)
    approval_queue_missing_total = _safe_int(summary.get("approval_queue_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tiered approval flow window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"tiered approval flow event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if high_risk_approval_coverage_ratio < max(0.0, float(min_high_risk_approval_coverage_ratio)):
        failures.append(
            "tiered approval flow high-risk approval coverage ratio below minimum: "
            f"{high_risk_approval_coverage_ratio:.4f} < {float(min_high_risk_approval_coverage_ratio):.4f}"
        )
    if low_risk_auto_ratio < max(0.0, float(min_low_risk_auto_ratio)):
        failures.append(
            f"tiered approval flow low-risk auto ratio below minimum: {low_risk_auto_ratio:.4f} < {float(min_low_risk_auto_ratio):.4f}"
        )
    if missing_band_total > max(0, int(max_missing_band_total)):
        failures.append(f"tiered approval flow missing-band total exceeded: {missing_band_total} > {int(max_missing_band_total)}")
    if unsafe_auto_high_risk_total > max(0, int(max_unsafe_auto_high_risk_total)):
        failures.append(
            "tiered approval flow unsafe-auto high-risk total exceeded: "
            f"{unsafe_auto_high_risk_total} > {int(max_unsafe_auto_high_risk_total)}"
        )
    if r3_auto_total > max(0, int(max_r3_auto_total)):
        failures.append(f"tiered approval flow R3 auto total exceeded: {r3_auto_total} > {int(max_r3_auto_total)}")
    if approval_queue_missing_total > max(0, int(max_approval_queue_missing_total)):
        failures.append(
            "tiered approval flow approval-queue-missing total exceeded: "
            f"{approval_queue_missing_total} > {int(max_approval_queue_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tiered approval flow stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Answer Tiered Approval Flow Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(
        f"- high_risk_approval_coverage_ratio: {_safe_float(summary.get('high_risk_approval_coverage_ratio'), 0.0):.4f}"
    )
    lines.append(f"- unsafe_auto_high_risk_total: {_safe_int(summary.get('unsafe_auto_high_risk_total'), 0)}")
    lines.append(f"- r3_auto_total: {_safe_int(summary.get('r3_auto_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate tiered approval flow enforcement by risk band.")
    parser.add_argument("--events-jsonl", default="var/risk_banding/tiered_approval_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_answer_tiered_approval_flow_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-high-risk-approval-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-low-risk-auto-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-band-total", type=int, default=1000000)
    parser.add_argument("--max-unsafe-auto-high-risk-total", type=int, default=1000000)
    parser.add_argument("--max-r3-auto-total", type=int, default=1000000)
    parser.add_argument("--max-approval-queue-missing-total", type=int, default=1000000)
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
    summary = summarize_answer_tiered_approval_flow_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_high_risk_approval_coverage_ratio=max(0.0, float(args.min_high_risk_approval_coverage_ratio)),
        min_low_risk_auto_ratio=max(0.0, float(args.min_low_risk_auto_ratio)),
        max_missing_band_total=max(0, int(args.max_missing_band_total)),
        max_unsafe_auto_high_risk_total=max(0, int(args.max_unsafe_auto_high_risk_total)),
        max_r3_auto_total=max(0, int(args.max_r3_auto_total)),
        max_approval_queue_missing_total=max(0, int(args.max_approval_queue_missing_total)),
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
                "min_high_risk_approval_coverage_ratio": float(args.min_high_risk_approval_coverage_ratio),
                "min_low_risk_auto_ratio": float(args.min_low_risk_auto_ratio),
                "max_missing_band_total": int(args.max_missing_band_total),
                "max_unsafe_auto_high_risk_total": int(args.max_unsafe_auto_high_risk_total),
                "max_r3_auto_total": int(args.max_r3_auto_total),
                "max_approval_queue_missing_total": int(args.max_approval_queue_missing_total),
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
    print(f"high_risk_approval_coverage_ratio={_safe_float(summary.get('high_risk_approval_coverage_ratio'), 0.0):.4f}")
    print(f"unsafe_auto_high_risk_total={_safe_int(summary.get('unsafe_auto_high_risk_total'), 0)}")
    print(f"approval_queue_missing_total={_safe_int(summary.get('approval_queue_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
