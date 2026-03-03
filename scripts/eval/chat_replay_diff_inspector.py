#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_DIVERGENCE_TYPES = {"POLICY", "TOOL_IO", "PROMPT", "BUDGET", "STATE", "OUTPUT"}


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


def _extract_first_divergence(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    direct = row.get("first_divergence")
    if isinstance(direct, Mapping):
        return direct
    diff = row.get("diff")
    if isinstance(diff, Mapping):
        nested = diff.get("first_divergence")
        if isinstance(nested, Mapping):
            return nested
    return None


def _is_divergence_detected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("divergence_detected"), False):
        return True
    diff = row.get("diff")
    if isinstance(diff, Mapping):
        if diff.get("matched") is False:
            return True
    if _safe_bool(row.get("matched"), True) is False:
        return True
    status = str(row.get("status") or "").strip().upper()
    return status in {"MISMATCH", "DIVERGED"}


def summarize_diff_inspector(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    divergence_detected_total = 0
    matched_total = 0
    first_divergence_total = 0
    missing_first_divergence_total = 0
    unknown_divergence_type_total = 0
    invalid_step_total = 0
    divergence_type_distribution: dict[str, int] = {}

    for row in rows:
        run_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        divergence_detected = _is_divergence_detected(row)
        if not divergence_detected:
            matched_total += 1
            continue
        divergence_detected_total += 1

        first_div = _extract_first_divergence(row)
        if not isinstance(first_div, Mapping):
            missing_first_divergence_total += 1
            continue

        first_divergence_total += 1
        divergence_type = str(first_div.get("type") or first_div.get("divergence_type") or "").strip().upper()
        if divergence_type not in VALID_DIVERGENCE_TYPES:
            unknown_divergence_type_total += 1
            divergence_type = divergence_type or "UNKNOWN"
        divergence_type_distribution[divergence_type] = divergence_type_distribution.get(divergence_type, 0) + 1

        step = _safe_int(first_div.get("step") or first_div.get("turn"), 0)
        if step <= 0:
            invalid_step_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "matched_total": matched_total,
        "divergence_detected_total": divergence_detected_total,
        "first_divergence_total": first_divergence_total,
        "missing_first_divergence_total": missing_first_divergence_total,
        "unknown_divergence_type_total": unknown_divergence_type_total,
        "invalid_step_total": invalid_step_total,
        "divergence_type_distribution": [
            {"type": key, "count": value} for key, value in sorted(divergence_type_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_divergence_detected_total: int,
    max_missing_first_divergence_total: int,
    max_unknown_divergence_type_total: int,
    max_invalid_step_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    divergence_detected_total = _safe_int(summary.get("divergence_detected_total"), 0)
    missing_first_divergence_total = _safe_int(summary.get("missing_first_divergence_total"), 0)
    unknown_divergence_type_total = _safe_int(summary.get("unknown_divergence_type_total"), 0)
    invalid_step_total = _safe_int(summary.get("invalid_step_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"replay diff inspector window too small: {window_size} < {int(min_window)}")
    if divergence_detected_total < max(0, int(min_divergence_detected_total)):
        failures.append(
            f"replay diff divergence total too small: {divergence_detected_total} < {int(min_divergence_detected_total)}"
        )
    if window_size == 0:
        return failures

    if missing_first_divergence_total > max(0, int(max_missing_first_divergence_total)):
        failures.append(
            "replay diff missing first divergence total exceeded: "
            f"{missing_first_divergence_total} > {int(max_missing_first_divergence_total)}"
        )
    if unknown_divergence_type_total > max(0, int(max_unknown_divergence_type_total)):
        failures.append(
            "replay diff unknown divergence type total exceeded: "
            f"{unknown_divergence_type_total} > {int(max_unknown_divergence_type_total)}"
        )
    if invalid_step_total > max(0, int(max_invalid_step_total)):
        failures.append(f"replay diff invalid divergence step total exceeded: {invalid_step_total} > {int(max_invalid_step_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"replay diff inspector stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Replay Diff Inspector")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- divergence_detected_total: {_safe_int(summary.get('divergence_detected_total'), 0)}")
    lines.append(f"- first_divergence_total: {_safe_int(summary.get('first_divergence_total'), 0)}")
    lines.append(f"- missing_first_divergence_total: {_safe_int(summary.get('missing_first_divergence_total'), 0)}")
    lines.append(f"- unknown_divergence_type_total: {_safe_int(summary.get('unknown_divergence_type_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate replay diff inspector quality.")
    parser.add_argument("--events-jsonl", default="var/chat_graph/replay/diff_inspector_runs.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_replay_diff_inspector")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-divergence-detected-total", type=int, default=0)
    parser.add_argument("--max-missing-first-divergence-total", type=int, default=0)
    parser.add_argument("--max-unknown-divergence-type-total", type=int, default=0)
    parser.add_argument("--max-invalid-step-total", type=int, default=0)
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
    summary = summarize_diff_inspector(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_divergence_detected_total=max(0, int(args.min_divergence_detected_total)),
        max_missing_first_divergence_total=max(0, int(args.max_missing_first_divergence_total)),
        max_unknown_divergence_type_total=max(0, int(args.max_unknown_divergence_type_total)),
        max_invalid_step_total=max(0, int(args.max_invalid_step_total)),
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
                "min_divergence_detected_total": int(args.min_divergence_detected_total),
                "max_missing_first_divergence_total": int(args.max_missing_first_divergence_total),
                "max_unknown_divergence_type_total": int(args.max_unknown_divergence_type_total),
                "max_invalid_step_total": int(args.max_invalid_step_total),
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
    print(f"divergence_detected_total={_safe_int(summary.get('divergence_detected_total'), 0)}")
    print(f"missing_first_divergence_total={_safe_int(summary.get('missing_first_divergence_total'), 0)}")
    print(f"unknown_divergence_type_total={_safe_int(summary.get('unknown_divergence_type_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
