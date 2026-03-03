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


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _status_success(row: Mapping[str, Any]) -> bool | None:
    parsed = _safe_bool(row.get("success"))
    if parsed is not None:
        return parsed
    status = _normalize_token(row.get("status") or row.get("result"))
    if status in {"SUCCESS", "SUCCEEDED", "OK", "DONE", "COMPLETED"}:
        return True
    if status in {"FAIL", "FAILED", "ERROR", "TIMEOUT", "CANCELLED"}:
        return False
    return None


def _latency_ms(row: Mapping[str, Any]) -> float | None:
    for key in ("latency_ms", "response_ms", "duration_ms", "elapsed_ms"):
        if key in row:
            return max(0.0, _safe_float(row.get(key), 0.0))
    return None


def _tool_name(row: Mapping[str, Any]) -> str:
    return str(row.get("tool") or row.get("tool_name") or row.get("target_tool") or "").strip()


def summarize_tool_health_score_guard(
    rows: list[Mapping[str, Any]],
    *,
    max_latency_p95_ms: float,
    max_error_ratio: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    tool_rows: dict[str, list[Mapping[str, Any]]] = {}
    missing_telemetry_total = 0
    event_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        tool = _tool_name(row)
        if not tool:
            continue
        event_total += 1
        tool_rows.setdefault(tool, []).append(row)

        if _status_success(row) is None or _latency_ms(row) is None:
            missing_telemetry_total += 1

    max_latency = max(1.0, float(max_latency_p95_ms))
    max_error = max(0.000001, float(max_error_ratio))

    unhealthy_tool_total = 0
    tool_health_rows: list[dict[str, Any]] = []
    health_scores: list[float] = []

    for tool, items in sorted(tool_rows.items(), key=lambda item: item[0]):
        success_total = 0
        fail_total = 0
        latencies: list[float] = []
        transitions = 0
        prev_status: bool | None = None

        for row in items:
            st = _status_success(row)
            latency = _latency_ms(row)
            if st is True:
                success_total += 1
            elif st is False:
                fail_total += 1
            if latency is not None:
                latencies.append(latency)

            if st is not None:
                if prev_status is not None and prev_status != st:
                    transitions += 1
                prev_status = st

        sample_total = success_total + fail_total
        success_ratio = 1.0 if sample_total == 0 else float(success_total) / float(sample_total)
        error_ratio = 0.0 if sample_total == 0 else float(fail_total) / float(sample_total)
        latency_p95_ms = _p95(latencies)
        volatility_ratio = 0.0 if sample_total <= 1 else float(transitions) / float(sample_total - 1)

        latency_score = max(0.0, 1.0 - (latency_p95_ms / max_latency))
        error_score = max(0.0, 1.0 - (error_ratio / max_error))
        volatility_score = max(0.0, 1.0 - volatility_ratio)
        health_score = (
            0.45 * success_ratio + 0.30 * latency_score + 0.15 * error_score + 0.10 * volatility_score
        )
        health_scores.append(health_score)

        tool_health_rows.append(
            {
                "tool": tool,
                "event_total": len(items),
                "sample_total": sample_total,
                "success_ratio": success_ratio,
                "error_ratio": error_ratio,
                "latency_p95_ms": latency_p95_ms,
                "volatility_ratio": volatility_ratio,
                "health_score": health_score,
            }
        )

    average_health_score = 0.0 if not health_scores else float(sum(health_scores)) / float(len(health_scores))
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "tool_total": len(tool_rows),
        "tool_health": tool_health_rows,
        "average_health_score": average_health_score,
        "unhealthy_tool_total": unhealthy_tool_total,
        "missing_telemetry_total": missing_telemetry_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_tool_total: int,
    min_tool_health_score: float,
    min_average_health_score: float,
    max_unhealthy_tool_total: int,
    max_missing_telemetry_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    tool_total = _safe_int(summary.get("tool_total"), 0)
    average_health_score = _safe_float(summary.get("average_health_score"), 0.0)
    missing_telemetry_total = _safe_int(summary.get("missing_telemetry_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    tool_health = summary.get("tool_health")
    unhealthy_tool_total = 0
    if isinstance(tool_health, list):
        threshold = max(0.0, min(1.0, float(min_tool_health_score)))
        for item in tool_health:
            if not isinstance(item, Mapping):
                continue
            if _safe_float(item.get("health_score"), 0.0) < threshold:
                unhealthy_tool_total += 1

    if window_size < max(0, int(min_window)):
        failures.append(f"tool health window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"tool health event total too small: {event_total} < {int(min_event_total)}")
    if tool_total < max(0, int(min_tool_total)):
        failures.append(f"tool health tool total too small: {tool_total} < {int(min_tool_total)}")
    if window_size == 0:
        return failures

    if average_health_score < max(0.0, float(min_average_health_score)):
        failures.append(
            f"tool health average score below minimum: {average_health_score:.4f} < {float(min_average_health_score):.4f}"
        )
    if unhealthy_tool_total > max(0, int(max_unhealthy_tool_total)):
        failures.append(f"tool health unhealthy tool total exceeded: {unhealthy_tool_total} > {int(max_unhealthy_tool_total)}")
    if missing_telemetry_total > max(0, int(max_missing_telemetry_total)):
        failures.append(
            f"tool health missing telemetry total exceeded: {missing_telemetry_total} > {int(max_missing_telemetry_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool health stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Health Score Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- tool_total: {_safe_int(summary.get('tool_total'), 0)}")
    lines.append(f"- average_health_score: {_safe_float(summary.get('average_health_score'), 0.0):.4f}")
    lines.append(f"- missing_telemetry_total: {_safe_int(summary.get('missing_telemetry_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate tool health scoring quality.")
    parser.add_argument("--events-jsonl", default="var/tool_health/tool_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_health_score_guard")
    parser.add_argument("--max-latency-p95-ms", type=float, default=1500.0)
    parser.add_argument("--max-error-ratio", type=float, default=0.20)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-tool-total", type=int, default=0)
    parser.add_argument("--min-tool-health-score", type=float, default=0.0)
    parser.add_argument("--min-average-health-score", type=float, default=0.0)
    parser.add_argument("--max-unhealthy-tool-total", type=int, default=1000000)
    parser.add_argument("--max-missing-telemetry-total", type=int, default=1000000)
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
    summary = summarize_tool_health_score_guard(
        rows,
        max_latency_p95_ms=max(1.0, float(args.max_latency_p95_ms)),
        max_error_ratio=max(0.000001, float(args.max_error_ratio)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_tool_total=max(0, int(args.min_tool_total)),
        min_tool_health_score=max(0.0, min(1.0, float(args.min_tool_health_score))),
        min_average_health_score=max(0.0, min(1.0, float(args.min_average_health_score))),
        max_unhealthy_tool_total=max(0, int(args.max_unhealthy_tool_total)),
        max_missing_telemetry_total=max(0, int(args.max_missing_telemetry_total)),
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
                "max_latency_p95_ms": float(args.max_latency_p95_ms),
                "max_error_ratio": float(args.max_error_ratio),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_tool_total": int(args.min_tool_total),
                "min_tool_health_score": float(args.min_tool_health_score),
                "min_average_health_score": float(args.min_average_health_score),
                "max_unhealthy_tool_total": int(args.max_unhealthy_tool_total),
                "max_missing_telemetry_total": int(args.max_missing_telemetry_total),
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
    print(f"tool_total={_safe_int(summary.get('tool_total'), 0)}")
    print(f"average_health_score={_safe_float(summary.get('average_health_score'), 0.0):.4f}")
    print(f"missing_telemetry_total={_safe_int(summary.get('missing_telemetry_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
