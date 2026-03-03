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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _confidence(row: Mapping[str, Any]) -> float:
    for key in ("calibrated_confidence", "confidence_calibrated", "intent_calibrated_confidence", "intent_confidence", "confidence"):
        if key in row:
            return max(0.0, min(1.0, _safe_float(row.get(key), 0.0)))
    return 0.0


def _route_category(row: Mapping[str, Any]) -> str:
    token = _normalize_token(
        row.get("route")
        or row.get("route_decision")
        or row.get("policy_route")
        or row.get("decision")
        or row.get("next_action")
    )
    if token in {"TOOL", "EXECUTE_TOOL", "EXECUTE", "LOOKUP", "WRITE", "ACTION_EXECUTE", "EXECUTE_ACTION"}:
        return "TOOL"
    if token in {"CLARIFY", "ASK", "ASK_SLOT", "ASK_CLARIFICATION", "OPTIONS", "CONFIRM"}:
        return "CLARIFY"
    if token in {"HANDOFF", "ESCALATE", "TICKET", "OPEN_TICKET", "OPEN_SUPPORT_TICKET", "TRANSFER_AGENT"}:
        return "HANDOFF"
    return "UNKNOWN"


def _is_repeat_low_confidence(row: Mapping[str, Any], repeat_threshold: int) -> bool:
    if _safe_bool(row.get("repeat_low_confidence"), False):
        return True
    if _safe_bool(row.get("consecutive_low_confidence"), False):
        return True
    repeat_count = _safe_int(
        row.get("low_confidence_repeat_count") or row.get("repeat_count") or row.get("consecutive_low_confidence_count"),
        0,
    )
    return repeat_count >= max(1, int(repeat_threshold))


def summarize_intent_confidence_routing_guard(
    rows: list[Mapping[str, Any]],
    *,
    tool_route_threshold: float,
    clarify_route_threshold: float,
    repeat_low_confidence_threshold: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    decision_total = 0
    high_confidence_total = 0
    mid_confidence_total = 0
    low_confidence_total = 0
    routing_mismatch_total = 0
    unsafe_tool_route_total = 0
    low_confidence_clarification_total = 0
    low_confidence_handoff_total = 0
    repeat_low_confidence_total = 0
    repeat_low_confidence_handoff_total = 0
    repeat_low_confidence_unescalated_total = 0
    intent_stats: dict[str, dict[str, int]] = {}

    tool_th = max(0.0, min(1.0, float(tool_route_threshold)))
    clarify_th = max(0.0, min(tool_th, float(clarify_route_threshold)))

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        route = _route_category(row)
        if route == "UNKNOWN":
            continue

        decision_total += 1
        intent = _normalize_token(row.get("intent") or row.get("predicted_intent") or "UNKNOWN")
        stat = intent_stats.setdefault(intent, {"count": 0, "mismatch_total": 0, "unsafe_tool_route_total": 0})
        stat["count"] += 1

        confidence = _confidence(row)
        if confidence >= tool_th:
            expected = "TOOL"
            high_confidence_total += 1
        elif confidence >= clarify_th:
            expected = "CLARIFY"
            mid_confidence_total += 1
        else:
            expected = "HANDOFF"
            low_confidence_total += 1

        allowed = {expected}
        if expected == "CLARIFY":
            # handoff is stricter than clarification and still safe.
            allowed.add("HANDOFF")

        if route not in allowed:
            routing_mismatch_total += 1
            stat["mismatch_total"] += 1

        if route == "TOOL" and confidence < tool_th:
            unsafe_tool_route_total += 1
            stat["unsafe_tool_route_total"] += 1

        if confidence < clarify_th:
            if route == "CLARIFY":
                low_confidence_clarification_total += 1
            if route == "HANDOFF":
                low_confidence_handoff_total += 1

        if _is_repeat_low_confidence(row, repeat_low_confidence_threshold):
            repeat_low_confidence_total += 1
            if route == "HANDOFF":
                repeat_low_confidence_handoff_total += 1
            else:
                repeat_low_confidence_unescalated_total += 1

    routing_mismatch_ratio = 0.0 if decision_total == 0 else float(routing_mismatch_total) / float(decision_total)
    low_confidence_clarification_ratio = (
        1.0 if low_confidence_total == 0 else float(low_confidence_clarification_total) / float(low_confidence_total)
    )
    repeat_low_confidence_handoff_ratio = (
        1.0
        if repeat_low_confidence_total == 0
        else float(repeat_low_confidence_handoff_total) / float(repeat_low_confidence_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    intent_distribution = []
    for intent, values in sorted(intent_stats.items(), key=lambda item: item[0]):
        count = _safe_int(values.get("count"), 0)
        mismatch_total = _safe_int(values.get("mismatch_total"), 0)
        unsafe_total = _safe_int(values.get("unsafe_tool_route_total"), 0)
        intent_distribution.append(
            {
                "intent": intent,
                "count": count,
                "mismatch_total": mismatch_total,
                "mismatch_ratio": 0.0 if count == 0 else float(mismatch_total) / float(count),
                "unsafe_tool_route_total": unsafe_total,
            }
        )

    return {
        "window_size": len(rows),
        "decision_total": decision_total,
        "high_confidence_total": high_confidence_total,
        "mid_confidence_total": mid_confidence_total,
        "low_confidence_total": low_confidence_total,
        "routing_mismatch_total": routing_mismatch_total,
        "routing_mismatch_ratio": routing_mismatch_ratio,
        "unsafe_tool_route_total": unsafe_tool_route_total,
        "low_confidence_clarification_total": low_confidence_clarification_total,
        "low_confidence_handoff_total": low_confidence_handoff_total,
        "low_confidence_clarification_ratio": low_confidence_clarification_ratio,
        "repeat_low_confidence_total": repeat_low_confidence_total,
        "repeat_low_confidence_handoff_total": repeat_low_confidence_handoff_total,
        "repeat_low_confidence_handoff_ratio": repeat_low_confidence_handoff_ratio,
        "repeat_low_confidence_unescalated_total": repeat_low_confidence_unescalated_total,
        "intent_distribution": intent_distribution,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_decision_total: int,
    max_routing_mismatch_ratio: float,
    max_unsafe_tool_route_total: int,
    min_low_confidence_clarification_ratio: float,
    min_repeat_low_confidence_handoff_ratio: float,
    max_repeat_low_confidence_unescalated_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    decision_total = _safe_int(summary.get("decision_total"), 0)
    routing_mismatch_ratio = _safe_float(summary.get("routing_mismatch_ratio"), 0.0)
    unsafe_tool_route_total = _safe_int(summary.get("unsafe_tool_route_total"), 0)
    low_confidence_clarification_ratio = _safe_float(summary.get("low_confidence_clarification_ratio"), 0.0)
    repeat_low_confidence_handoff_ratio = _safe_float(summary.get("repeat_low_confidence_handoff_ratio"), 0.0)
    repeat_low_confidence_unescalated_total = _safe_int(summary.get("repeat_low_confidence_unescalated_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"intent routing window too small: {window_size} < {int(min_window)}")
    if decision_total < max(0, int(min_decision_total)):
        failures.append(f"intent routing decision total too small: {decision_total} < {int(min_decision_total)}")
    if window_size == 0:
        return failures

    if routing_mismatch_ratio > max(0.0, float(max_routing_mismatch_ratio)):
        failures.append(
            f"intent routing mismatch ratio exceeded: {routing_mismatch_ratio:.4f} > {float(max_routing_mismatch_ratio):.4f}"
        )
    if unsafe_tool_route_total > max(0, int(max_unsafe_tool_route_total)):
        failures.append(
            f"intent routing unsafe tool route total exceeded: {unsafe_tool_route_total} > {int(max_unsafe_tool_route_total)}"
        )
    if low_confidence_clarification_ratio < max(0.0, float(min_low_confidence_clarification_ratio)):
        failures.append(
            "intent routing low-confidence clarification ratio below minimum: "
            f"{low_confidence_clarification_ratio:.4f} < {float(min_low_confidence_clarification_ratio):.4f}"
        )
    if repeat_low_confidence_handoff_ratio < max(0.0, float(min_repeat_low_confidence_handoff_ratio)):
        failures.append(
            "intent routing repeat low-confidence handoff ratio below minimum: "
            f"{repeat_low_confidence_handoff_ratio:.4f} < {float(min_repeat_low_confidence_handoff_ratio):.4f}"
        )
    if repeat_low_confidence_unescalated_total > max(0, int(max_repeat_low_confidence_unescalated_total)):
        failures.append(
            "intent routing repeat low-confidence unescalated total exceeded: "
            f"{repeat_low_confidence_unescalated_total} > {int(max_repeat_low_confidence_unescalated_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"intent routing stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Intent Confidence Routing Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- decision_total: {_safe_int(summary.get('decision_total'), 0)}")
    lines.append(f"- routing_mismatch_ratio: {_safe_float(summary.get('routing_mismatch_ratio'), 0.0):.4f}")
    lines.append(f"- unsafe_tool_route_total: {_safe_int(summary.get('unsafe_tool_route_total'), 0)}")
    lines.append(
        f"- repeat_low_confidence_handoff_ratio: {_safe_float(summary.get('repeat_low_confidence_handoff_ratio'), 0.0):.4f}"
    )
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
    parser = argparse.ArgumentParser(description="Evaluate confidence-threshold-based intent routing quality.")
    parser.add_argument("--events-jsonl", default="var/intent_calibration/routing_decisions.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_intent_confidence_routing_guard")
    parser.add_argument("--tool-route-threshold", type=float, default=0.75)
    parser.add_argument("--clarify-route-threshold", type=float, default=0.45)
    parser.add_argument("--repeat-low-confidence-threshold", type=int, default=3)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-decision-total", type=int, default=0)
    parser.add_argument("--max-routing-mismatch-ratio", type=float, default=1000000.0)
    parser.add_argument("--max-unsafe-tool-route-total", type=int, default=1000000)
    parser.add_argument("--min-low-confidence-clarification-ratio", type=float, default=0.0)
    parser.add_argument("--min-repeat-low-confidence-handoff-ratio", type=float, default=0.0)
    parser.add_argument("--max-repeat-low-confidence-unescalated-total", type=int, default=1000000)
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
    summary = summarize_intent_confidence_routing_guard(
        rows,
        tool_route_threshold=max(0.0, min(1.0, float(args.tool_route_threshold))),
        clarify_route_threshold=max(0.0, min(1.0, float(args.clarify_route_threshold))),
        repeat_low_confidence_threshold=max(1, int(args.repeat_low_confidence_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_decision_total=max(0, int(args.min_decision_total)),
        max_routing_mismatch_ratio=max(0.0, float(args.max_routing_mismatch_ratio)),
        max_unsafe_tool_route_total=max(0, int(args.max_unsafe_tool_route_total)),
        min_low_confidence_clarification_ratio=max(0.0, float(args.min_low_confidence_clarification_ratio)),
        min_repeat_low_confidence_handoff_ratio=max(0.0, float(args.min_repeat_low_confidence_handoff_ratio)),
        max_repeat_low_confidence_unescalated_total=max(0, int(args.max_repeat_low_confidence_unescalated_total)),
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
                "tool_route_threshold": float(args.tool_route_threshold),
                "clarify_route_threshold": float(args.clarify_route_threshold),
                "repeat_low_confidence_threshold": int(args.repeat_low_confidence_threshold),
                "min_window": int(args.min_window),
                "min_decision_total": int(args.min_decision_total),
                "max_routing_mismatch_ratio": float(args.max_routing_mismatch_ratio),
                "max_unsafe_tool_route_total": int(args.max_unsafe_tool_route_total),
                "min_low_confidence_clarification_ratio": float(args.min_low_confidence_clarification_ratio),
                "min_repeat_low_confidence_handoff_ratio": float(args.min_repeat_low_confidence_handoff_ratio),
                "max_repeat_low_confidence_unescalated_total": int(args.max_repeat_low_confidence_unescalated_total),
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
    print(f"decision_total={_safe_int(summary.get('decision_total'), 0)}")
    print(f"routing_mismatch_ratio={_safe_float(summary.get('routing_mismatch_ratio'), 0.0):.4f}")
    print(f"unsafe_tool_route_total={_safe_int(summary.get('unsafe_tool_route_total'), 0)}")
    print(
        "repeat_low_confidence_handoff_ratio="
        f"{_safe_float(summary.get('repeat_low_confidence_handoff_ratio'), 0.0):.4f}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
