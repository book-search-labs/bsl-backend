#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


SUCCESS_STATUSES = {"SUCCESS", "SUCCEEDED", "OK", "DONE", "COMPLETED"}
FAIL_STATUSES = {"FAIL", "FAILED", "ERROR", "TIMEOUT", "CANCELLED"}
SAFE_FALLBACK_RESULTS = {"SAFE_FALLBACK", "HANDOFF", "OPEN_TICKET", "CLARIFY", "ASK", "ABSTAIN"}


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


def _request_id(row: Mapping[str, Any]) -> str:
    return str(row.get("request_id") or row.get("trace_id") or row.get("conversation_turn_id") or "").strip()


def _attempt_no(row: Mapping[str, Any]) -> int:
    if row.get("attempt_no") is not None:
        return _safe_int(row.get("attempt_no"), 0)
    if row.get("attempt_index") is not None:
        return _safe_int(row.get("attempt_index"), 0)
    if row.get("retry_count") is not None:
        return _safe_int(row.get("retry_count"), 0)
    return 0


def _tool(row: Mapping[str, Any]) -> str:
    return str(row.get("tool") or row.get("selected_tool") or row.get("route_tool") or "").strip()


def _is_success(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("success"))
    if explicit is not None:
        return explicit
    status = _normalize_token(row.get("status") or row.get("result"))
    if status in SUCCESS_STATUSES:
        return True
    if status in FAIL_STATUSES:
        return False
    return False


def _safe_fallback(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("safe_fallback_applied"))
    if explicit is not None:
        return explicit
    explicit2 = _safe_bool(row.get("fallback_applied"))
    if explicit2 is not None and explicit2:
        return True
    result = _normalize_token(row.get("route_result") or row.get("next_action") or row.get("result"))
    return result in SAFE_FALLBACK_RESULTS


def summarize_tool_degrade_strategy_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        rid = _request_id(row)
        if not rid:
            continue
        grouped.setdefault(rid, []).append({str(k): v for k, v in row.items()})

    request_total = 0
    degrade_required_total = 0
    fallback_attempted_total = 0
    sequential_retry_success_total = 0
    safe_fallback_total = 0
    resolved_degrade_total = 0
    stalled_degrade_total = 0
    duplicate_tool_retry_total = 0

    request_rows: list[dict[str, Any]] = []

    for rid, events in sorted(grouped.items(), key=lambda item: item[0]):
        ordered = sorted(events, key=lambda row: (_attempt_no(row), _event_ts(row) or datetime.min.replace(tzinfo=timezone.utc)))
        if not ordered:
            continue
        request_total += 1

        primary = ordered[0]
        primary_tool = _tool(primary)
        primary_success = _is_success(primary)
        degrade_required = not primary_success

        later = ordered[1:]
        later_tools = [_tool(row) for row in later if _tool(row)]
        has_alt_tool = any(tool and tool != primary_tool for tool in later_tools)
        has_later_success = any(_is_success(row) for row in later)
        safe_fallback = any(_safe_fallback(row) for row in ordered)
        fallback_attempted = bool(later) or safe_fallback
        duplicate_tool_retry = bool(later_tools) and all(tool == primary_tool for tool in later_tools) and (not safe_fallback)

        sequential_retry_success = has_alt_tool and any(_is_success(row) and _tool(row) != primary_tool for row in later)

        if degrade_required:
            degrade_required_total += 1
            if fallback_attempted:
                fallback_attempted_total += 1
            if sequential_retry_success:
                sequential_retry_success_total += 1
            if safe_fallback:
                safe_fallback_total += 1
            if sequential_retry_success or safe_fallback:
                resolved_degrade_total += 1
            if (not sequential_retry_success) and (not safe_fallback):
                stalled_degrade_total += 1
            if duplicate_tool_retry:
                duplicate_tool_retry_total += 1

        request_rows.append(
            {
                "request_id": rid,
                "primary_tool": primary_tool or "NONE",
                "degrade_required": degrade_required,
                "fallback_attempted": fallback_attempted,
                "sequential_retry_success": sequential_retry_success,
                "safe_fallback": safe_fallback,
                "duplicate_tool_retry": duplicate_tool_retry,
            }
        )

    degrade_coverage_ratio = (
        1.0 if degrade_required_total == 0 else float(fallback_attempted_total) / float(degrade_required_total)
    )
    safe_fallback_ratio = (
        1.0
        if degrade_required_total == 0
        else float(resolved_degrade_total) / float(degrade_required_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "request_total": request_total,
        "degrade_required_total": degrade_required_total,
        "fallback_attempted_total": fallback_attempted_total,
        "degrade_coverage_ratio": degrade_coverage_ratio,
        "sequential_retry_success_total": sequential_retry_success_total,
        "safe_fallback_total": safe_fallback_total,
        "resolved_degrade_total": resolved_degrade_total,
        "safe_fallback_ratio": safe_fallback_ratio,
        "stalled_degrade_total": stalled_degrade_total,
        "duplicate_tool_retry_total": duplicate_tool_retry_total,
        "requests": request_rows,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_request_total: int,
    min_degrade_coverage_ratio: float,
    min_safe_fallback_ratio: float,
    max_stalled_degrade_total: int,
    max_duplicate_tool_retry_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    request_total = _safe_int(summary.get("request_total"), 0)
    degrade_coverage_ratio = _safe_float(summary.get("degrade_coverage_ratio"), 0.0)
    safe_fallback_ratio = _safe_float(summary.get("safe_fallback_ratio"), 0.0)
    stalled_degrade_total = _safe_int(summary.get("stalled_degrade_total"), 0)
    duplicate_tool_retry_total = _safe_int(summary.get("duplicate_tool_retry_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool degrade strategy window too small: {window_size} < {int(min_window)}")
    if request_total < max(0, int(min_request_total)):
        failures.append(f"tool degrade strategy request total too small: {request_total} < {int(min_request_total)}")
    if window_size == 0:
        return failures

    if degrade_coverage_ratio < max(0.0, float(min_degrade_coverage_ratio)):
        failures.append(
            f"tool degrade strategy coverage ratio below minimum: {degrade_coverage_ratio:.4f} < {float(min_degrade_coverage_ratio):.4f}"
        )
    if safe_fallback_ratio < max(0.0, float(min_safe_fallback_ratio)):
        failures.append(
            f"tool degrade strategy safe-fallback ratio below minimum: {safe_fallback_ratio:.4f} < {float(min_safe_fallback_ratio):.4f}"
        )
    if stalled_degrade_total > max(0, int(max_stalled_degrade_total)):
        failures.append(
            f"tool degrade strategy stalled total exceeded: {stalled_degrade_total} > {int(max_stalled_degrade_total)}"
        )
    if duplicate_tool_retry_total > max(0, int(max_duplicate_tool_retry_total)):
        failures.append(
            "tool degrade strategy duplicate-tool retry total exceeded: "
            f"{duplicate_tool_retry_total} > {int(max_duplicate_tool_retry_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool degrade strategy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Degrade Strategy Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- request_total: {_safe_int(summary.get('request_total'), 0)}")
    lines.append(f"- degrade_coverage_ratio: {_safe_float(summary.get('degrade_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- safe_fallback_ratio: {_safe_float(summary.get('safe_fallback_ratio'), 0.0):.4f}")
    lines.append(f"- stalled_degrade_total: {_safe_int(summary.get('stalled_degrade_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate tool degrade strategy safety and fallback quality.")
    parser.add_argument("--events-jsonl", default="var/tool_health/degrade_strategy_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_degrade_strategy_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-request-total", type=int, default=0)
    parser.add_argument("--min-degrade-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-safe-fallback-ratio", type=float, default=0.0)
    parser.add_argument("--max-stalled-degrade-total", type=int, default=1000000)
    parser.add_argument("--max-duplicate-tool-retry-total", type=int, default=1000000)
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
    summary = summarize_tool_degrade_strategy_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_request_total=max(0, int(args.min_request_total)),
        min_degrade_coverage_ratio=max(0.0, float(args.min_degrade_coverage_ratio)),
        min_safe_fallback_ratio=max(0.0, float(args.min_safe_fallback_ratio)),
        max_stalled_degrade_total=max(0, int(args.max_stalled_degrade_total)),
        max_duplicate_tool_retry_total=max(0, int(args.max_duplicate_tool_retry_total)),
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
                "min_request_total": int(args.min_request_total),
                "min_degrade_coverage_ratio": float(args.min_degrade_coverage_ratio),
                "min_safe_fallback_ratio": float(args.min_safe_fallback_ratio),
                "max_stalled_degrade_total": int(args.max_stalled_degrade_total),
                "max_duplicate_tool_retry_total": int(args.max_duplicate_tool_retry_total),
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
    print(f"request_total={_safe_int(summary.get('request_total'), 0)}")
    print(f"degrade_coverage_ratio={_safe_float(summary.get('degrade_coverage_ratio'), 0.0):.4f}")
    print(f"safe_fallback_ratio={_safe_float(summary.get('safe_fallback_ratio'), 0.0):.4f}")
    print(f"stalled_degrade_total={_safe_int(summary.get('stalled_degrade_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
