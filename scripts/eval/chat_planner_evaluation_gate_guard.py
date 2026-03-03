#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


BLOCK_DECISIONS = {"BLOCK", "ROLLBACK", "HOLD", "PARTIAL_ROLLBACK", "PARTIAL_ISOLATION"}
PARTIAL_ROLLBACK_DECISIONS = {"PARTIAL_ROLLBACK", "PARTIAL_ISOLATION", "ISOLATE_BUCKET"}


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


def _weight(row: Mapping[str, Any]) -> float:
    value = _safe_float(row.get("sample_count"), 1.0)
    return max(1.0, value)


def _rate_or_bool(row: Mapping[str, Any], *, rate_key: str, bool_key: str) -> float:
    if row.get(rate_key) is not None:
        return max(0.0, min(1.0, _safe_float(row.get(rate_key), 0.0)))
    return 1.0 if _safe_bool(row.get(bool_key)) else 0.0


def _intent(row: Mapping[str, Any]) -> str:
    value = str(row.get("intent") or row.get("intent_bucket") or "GENERAL").strip().upper()
    return value or "GENERAL"


def _release_blocked(row: Mapping[str, Any]) -> bool:
    if row.get("release_blocked") is not None:
        return _safe_bool(row.get("release_blocked"))
    decision = str(row.get("release_decision") or row.get("decision") or "").strip().upper()
    return decision in BLOCK_DECISIONS


def _partial_rollback_applied(row: Mapping[str, Any]) -> bool:
    if row.get("partial_rollback_applied") is not None:
        return _safe_bool(row.get("partial_rollback_applied"))
    decision = str(row.get("release_decision") or row.get("decision") or "").strip().upper()
    return decision in PARTIAL_ROLLBACK_DECISIONS


def summarize_planner_evaluation_gate_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    max_path_deviation_rate: float = 1.0,
    max_stage_omission_rate: float = 1.0,
    max_wrong_escalation_rate: float = 1.0,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    sample_total = 0.0
    path_deviation_total = 0.0
    stage_omission_total = 0.0
    wrong_escalation_total = 0.0
    missed_release_block_total = 0
    false_release_block_total = 0
    partial_rollback_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        weight = _weight(row)
        sample_total += weight

        path_rate = _rate_or_bool(row, rate_key="path_deviation_rate", bool_key="path_deviation")
        stage_rate = _rate_or_bool(row, rate_key="stage_omission_rate", bool_key="stage_omission")
        wrong_rate = _rate_or_bool(row, rate_key="wrong_escalation_rate", bool_key="wrong_escalation")

        path_deviation_total += weight * path_rate
        stage_omission_total += weight * stage_rate
        wrong_escalation_total += weight * wrong_rate

        exceeded = (
            path_rate > max(0.0, float(max_path_deviation_rate))
            or stage_rate > max(0.0, float(max_stage_omission_rate))
            or wrong_rate > max(0.0, float(max_wrong_escalation_rate))
        )
        blocked = _release_blocked(row)
        partial_rollback = _partial_rollback_applied(row)

        if exceeded:
            if not blocked:
                missed_release_block_total += 1
            if not partial_rollback:
                partial_rollback_missing_total += 1
        elif blocked:
            false_release_block_total += 1

    path_deviation_rate = 0.0 if sample_total == 0 else path_deviation_total / sample_total
    stage_omission_rate = 0.0 if sample_total == 0 else stage_omission_total / sample_total
    wrong_escalation_rate = 0.0 if sample_total == 0 else wrong_escalation_total / sample_total
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "sample_total": sample_total,
        "path_deviation_total": path_deviation_total,
        "stage_omission_total": stage_omission_total,
        "wrong_escalation_total": wrong_escalation_total,
        "path_deviation_rate": path_deviation_rate,
        "stage_omission_rate": stage_omission_rate,
        "wrong_escalation_rate": wrong_escalation_rate,
        "missed_release_block_total": missed_release_block_total,
        "false_release_block_total": false_release_block_total,
        "partial_rollback_missing_total": partial_rollback_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    max_path_deviation_rate: float,
    max_stage_omission_rate: float,
    max_wrong_escalation_rate: float,
    max_missed_release_block_total: int,
    max_false_release_block_total: int,
    max_partial_rollback_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    path_deviation_rate = _safe_float(summary.get("path_deviation_rate"), 0.0)
    stage_omission_rate = _safe_float(summary.get("stage_omission_rate"), 0.0)
    wrong_escalation_rate = _safe_float(summary.get("wrong_escalation_rate"), 0.0)
    missed_release_block_total = _safe_int(summary.get("missed_release_block_total"), 0)
    false_release_block_total = _safe_int(summary.get("false_release_block_total"), 0)
    partial_rollback_missing_total = _safe_int(summary.get("partial_rollback_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"planner evaluation window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"planner evaluation event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if path_deviation_rate > max(0.0, float(max_path_deviation_rate)):
        failures.append(
            f"planner evaluation path deviation rate exceeded: {path_deviation_rate:.4f} > {float(max_path_deviation_rate):.4f}"
        )
    if stage_omission_rate > max(0.0, float(max_stage_omission_rate)):
        failures.append(
            f"planner evaluation stage omission rate exceeded: {stage_omission_rate:.4f} > {float(max_stage_omission_rate):.4f}"
        )
    if wrong_escalation_rate > max(0.0, float(max_wrong_escalation_rate)):
        failures.append(
            f"planner evaluation wrong escalation rate exceeded: {wrong_escalation_rate:.4f} > {float(max_wrong_escalation_rate):.4f}"
        )
    if missed_release_block_total > max(0, int(max_missed_release_block_total)):
        failures.append(
            f"planner evaluation missed release block total exceeded: {missed_release_block_total} > {int(max_missed_release_block_total)}"
        )
    if false_release_block_total > max(0, int(max_false_release_block_total)):
        failures.append(
            f"planner evaluation false release block total exceeded: {false_release_block_total} > {int(max_false_release_block_total)}"
        )
    if partial_rollback_missing_total > max(0, int(max_partial_rollback_missing_total)):
        failures.append(
            "planner evaluation partial rollback missing total exceeded: "
            f"{partial_rollback_missing_total} > {int(max_partial_rollback_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"planner evaluation stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Planner Evaluation Gate Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- path_deviation_rate: {_safe_float(summary.get('path_deviation_rate'), 0.0):.4f}")
    lines.append(f"- stage_omission_rate: {_safe_float(summary.get('stage_omission_rate'), 0.0):.4f}")
    lines.append(f"- wrong_escalation_rate: {_safe_float(summary.get('wrong_escalation_rate'), 0.0):.4f}")
    lines.append(f"- missed_release_block_total: {_safe_int(summary.get('missed_release_block_total'), 0)}")
    lines.append(f"- false_release_block_total: {_safe_int(summary.get('false_release_block_total'), 0)}")
    lines.append(f"- partial_rollback_missing_total: {_safe_int(summary.get('partial_rollback_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate planner reliability release gate.")
    parser.add_argument("--events-jsonl", default="var/dialog_planner/planner_eval_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_planner_evaluation_gate_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--max-path-deviation-rate", type=float, default=1.0)
    parser.add_argument("--max-stage-omission-rate", type=float, default=1.0)
    parser.add_argument("--max-wrong-escalation-rate", type=float, default=1.0)
    parser.add_argument("--max-missed-release-block-total", type=int, default=1000000)
    parser.add_argument("--max-false-release-block-total", type=int, default=1000000)
    parser.add_argument("--max-partial-rollback-missing-total", type=int, default=1000000)
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
    summary = summarize_planner_evaluation_gate_guard(
        rows,
        max_path_deviation_rate=max(0.0, float(args.max_path_deviation_rate)),
        max_stage_omission_rate=max(0.0, float(args.max_stage_omission_rate)),
        max_wrong_escalation_rate=max(0.0, float(args.max_wrong_escalation_rate)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        max_path_deviation_rate=max(0.0, float(args.max_path_deviation_rate)),
        max_stage_omission_rate=max(0.0, float(args.max_stage_omission_rate)),
        max_wrong_escalation_rate=max(0.0, float(args.max_wrong_escalation_rate)),
        max_missed_release_block_total=max(0, int(args.max_missed_release_block_total)),
        max_false_release_block_total=max(0, int(args.max_false_release_block_total)),
        max_partial_rollback_missing_total=max(0, int(args.max_partial_rollback_missing_total)),
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
                "max_path_deviation_rate": float(args.max_path_deviation_rate),
                "max_stage_omission_rate": float(args.max_stage_omission_rate),
                "max_wrong_escalation_rate": float(args.max_wrong_escalation_rate),
                "max_missed_release_block_total": int(args.max_missed_release_block_total),
                "max_false_release_block_total": int(args.max_false_release_block_total),
                "max_partial_rollback_missing_total": int(args.max_partial_rollback_missing_total),
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
    print(f"path_deviation_rate={_safe_float(summary.get('path_deviation_rate'), 0.0):.4f}")
    print(f"stage_omission_rate={_safe_float(summary.get('stage_omission_rate'), 0.0):.4f}")
    print(f"wrong_escalation_rate={_safe_float(summary.get('wrong_escalation_rate'), 0.0):.4f}")
    print(f"missed_release_block_total={_safe_int(summary.get('missed_release_block_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
