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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _intent_group(row: Mapping[str, Any]) -> str:
    raw = str(row.get("intent_group") or row.get("intent_type") or row.get("intent") or "").strip().lower()
    if raw in {"commerce", "order", "refund", "payment"}:
        return "commerce"
    return "general"


def _completion_score(row: Mapping[str, Any]) -> float:
    completion_flag = _safe_bool(row.get("completed") or row.get("completion") or row.get("task_completed"))
    if completion_flag:
        return 1.0
    return _clamp01(_safe_float(row.get("completion_ratio"), 0.0))


def _computed_quality_score(row: Mapping[str, Any]) -> float:
    evidence = _clamp01(_safe_float(row.get("evidence_coverage_ratio"), 0.0))
    reask_rate = _clamp01(_safe_float(row.get("reask_rate"), 0.0))
    error_rate = _clamp01(_safe_float(row.get("error_rate"), 0.0))
    completion = _completion_score(row)

    if _intent_group(row) == "commerce":
        score = (
            0.40 * evidence
            + 0.30 * completion
            + 0.20 * (1.0 - error_rate)
            + 0.10 * (1.0 - reask_rate)
        )
    else:
        score = (
            0.35 * evidence
            + 0.25 * completion
            + 0.25 * (1.0 - error_rate)
            + 0.15 * (1.0 - reask_rate)
        )
    return _clamp01(score)


def _reported_quality_score(row: Mapping[str, Any]) -> float | None:
    value = row.get("session_quality_score")
    if value is None:
        value = row.get("quality_score")
    if value is None:
        return None
    return _clamp01(_safe_float(value, 0.0))


def summarize_session_quality_scorer_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    model_drift_tolerance: float = 0.05,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    scored_total = 0
    score_sum = 0.0
    low_quality_total = 0
    model_drift_total = 0
    commerce_scored_total = 0
    general_scored_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        computed_score = _computed_quality_score(row)
        scored_total += 1
        score_sum += computed_score
        if computed_score < 0.45:
            low_quality_total += 1

        group = _intent_group(row)
        if group == "commerce":
            commerce_scored_total += 1
        else:
            general_scored_total += 1

        reported = _reported_quality_score(row)
        if reported is not None and abs(reported - computed_score) > max(0.0, float(model_drift_tolerance)):
            model_drift_total += 1

    mean_quality_score = 0.0 if scored_total == 0 else score_sum / float(scored_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "scored_total": scored_total,
        "mean_quality_score": mean_quality_score,
        "low_quality_total": low_quality_total,
        "model_drift_total": model_drift_total,
        "commerce_scored_total": commerce_scored_total,
        "general_scored_total": general_scored_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_mean_quality_score: float,
    max_low_quality_total: int,
    max_model_drift_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    mean_quality_score = _safe_float(summary.get("mean_quality_score"), 0.0)
    low_quality_total = _safe_int(summary.get("low_quality_total"), 0)
    model_drift_total = _safe_int(summary.get("model_drift_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"session quality window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"session quality event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if mean_quality_score < max(0.0, float(min_mean_quality_score)):
        failures.append(
            f"session quality mean score below minimum: {mean_quality_score:.4f} < {float(min_mean_quality_score):.4f}"
        )
    if low_quality_total > max(0, int(max_low_quality_total)):
        failures.append(f"session quality low-quality total exceeded: {low_quality_total} > {int(max_low_quality_total)}")
    if model_drift_total > max(0, int(max_model_drift_total)):
        failures.append(f"session quality model-drift total exceeded: {model_drift_total} > {int(max_model_drift_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"session quality stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Session Quality Scorer Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- mean_quality_score: {_safe_float(summary.get('mean_quality_score'), 0.0):.4f}")
    lines.append(f"- low_quality_total: {_safe_int(summary.get('low_quality_total'), 0)}")
    lines.append(f"- model_drift_total: {_safe_int(summary.get('model_drift_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate session quality scorer.")
    parser.add_argument("--events-jsonl", default="var/session_quality/session_quality_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_session_quality_scorer_guard")
    parser.add_argument("--model-drift-tolerance", type=float, default=0.05)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-mean-quality-score", type=float, default=0.0)
    parser.add_argument("--max-low-quality-total", type=int, default=1000000)
    parser.add_argument("--max-model-drift-total", type=int, default=1000000)
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
    summary = summarize_session_quality_scorer_guard(
        rows,
        model_drift_tolerance=max(0.0, float(args.model_drift_tolerance)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_mean_quality_score=max(0.0, float(args.min_mean_quality_score)),
        max_low_quality_total=max(0, int(args.max_low_quality_total)),
        max_model_drift_total=max(0, int(args.max_model_drift_total)),
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
                "model_drift_tolerance": float(args.model_drift_tolerance),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_mean_quality_score": float(args.min_mean_quality_score),
                "max_low_quality_total": int(args.max_low_quality_total),
                "max_model_drift_total": int(args.max_model_drift_total),
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
    print(f"mean_quality_score={_safe_float(summary.get('mean_quality_score'), 0.0):.4f}")
    print(f"low_quality_total={_safe_int(summary.get('low_quality_total'), 0)}")
    print(f"model_drift_total={_safe_int(summary.get('model_drift_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
