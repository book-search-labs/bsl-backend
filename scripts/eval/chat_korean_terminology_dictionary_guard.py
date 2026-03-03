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


def _list_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, int(value))
    if isinstance(value, list):
        return len(value)
    text = str(value).strip()
    if not text:
        return 0
    if "," in text:
        return len([item for item in text.split(",") if item.strip()])
    return 1


def summarize_korean_terminology_dictionary_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    response_total = 0
    dictionary_version_missing_total = 0
    banned_term_violation_total = 0
    preferred_term_miss_total = 0
    synonym_normalization_applied_total = 0
    terminology_normalization_applied_total = 0
    conflict_term_total = 0

    for row in rows:
        response_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        version = str(row.get("terminology_dictionary_version") or row.get("dict_version") or "").strip()
        if not version:
            dictionary_version_missing_total += 1

        banned_count = _list_count(row.get("banned_term_hits") or row.get("forbidden_term_hits"))
        preferred_miss_count = _list_count(row.get("preferred_term_misses"))
        conflict_count = _list_count(row.get("term_conflicts"))

        banned_term_violation_total += banned_count
        preferred_term_miss_total += preferred_miss_count
        conflict_term_total += conflict_count

        synonym_applied = _safe_bool(row.get("synonym_normalization_applied"), False) or _list_count(
            row.get("synonym_replacements")
        ) > 0
        if synonym_applied:
            synonym_normalization_applied_total += 1

        terminology_applied = _safe_bool(row.get("term_normalization_applied"), False) or _list_count(
            row.get("term_replacements")
        ) > 0
        if terminology_applied:
            terminology_normalization_applied_total += 1

    dictionary_version_presence_ratio = (
        1.0 if response_total == 0 else float(response_total - dictionary_version_missing_total) / float(response_total)
    )
    normalization_ratio = (
        1.0 if response_total == 0 else float(terminology_normalization_applied_total) / float(response_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "response_total": response_total,
        "dictionary_version_missing_total": dictionary_version_missing_total,
        "dictionary_version_presence_ratio": dictionary_version_presence_ratio,
        "banned_term_violation_total": banned_term_violation_total,
        "preferred_term_miss_total": preferred_term_miss_total,
        "synonym_normalization_applied_total": synonym_normalization_applied_total,
        "terminology_normalization_applied_total": terminology_normalization_applied_total,
        "normalization_ratio": normalization_ratio,
        "conflict_term_total": conflict_term_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_response_total: int,
    min_dictionary_version_presence_ratio: float,
    min_normalization_ratio: float,
    max_banned_term_violation_total: int,
    max_preferred_term_miss_total: int,
    max_conflict_term_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    response_total = _safe_int(summary.get("response_total"), 0)
    dictionary_version_presence_ratio = _safe_float(summary.get("dictionary_version_presence_ratio"), 0.0)
    normalization_ratio = _safe_float(summary.get("normalization_ratio"), 0.0)
    banned_term_violation_total = _safe_int(summary.get("banned_term_violation_total"), 0)
    preferred_term_miss_total = _safe_int(summary.get("preferred_term_miss_total"), 0)
    conflict_term_total = _safe_int(summary.get("conflict_term_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat korean terminology window too small: {window_size} < {int(min_window)}")
    if response_total < max(0, int(min_response_total)):
        failures.append(f"chat korean terminology response total too small: {response_total} < {int(min_response_total)}")
    if window_size == 0:
        return failures

    if dictionary_version_presence_ratio < max(0.0, float(min_dictionary_version_presence_ratio)):
        failures.append(
            "chat korean terminology dictionary version presence ratio below minimum: "
            f"{dictionary_version_presence_ratio:.4f} < {float(min_dictionary_version_presence_ratio):.4f}"
        )
    if normalization_ratio < max(0.0, float(min_normalization_ratio)):
        failures.append(
            f"chat korean terminology normalization ratio below minimum: {normalization_ratio:.4f} < {float(min_normalization_ratio):.4f}"
        )
    if banned_term_violation_total > max(0, int(max_banned_term_violation_total)):
        failures.append(
            f"chat korean terminology banned-term violation total exceeded: {banned_term_violation_total} > {int(max_banned_term_violation_total)}"
        )
    if preferred_term_miss_total > max(0, int(max_preferred_term_miss_total)):
        failures.append(
            f"chat korean terminology preferred-term miss total exceeded: {preferred_term_miss_total} > {int(max_preferred_term_miss_total)}"
        )
    if conflict_term_total > max(0, int(max_conflict_term_total)):
        failures.append(
            f"chat korean terminology conflict term total exceeded: {conflict_term_total} > {int(max_conflict_term_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat korean terminology stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Terminology Dictionary Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- response_total: {_safe_int(summary.get('response_total'), 0)}")
    lines.append(f"- dictionary_version_presence_ratio: {_safe_float(summary.get('dictionary_version_presence_ratio'), 0.0):.4f}")
    lines.append(f"- normalization_ratio: {_safe_float(summary.get('normalization_ratio'), 0.0):.4f}")
    lines.append(f"- banned_term_violation_total: {_safe_int(summary.get('banned_term_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat korean terminology dictionary governance quality.")
    parser.add_argument("--events-jsonl", default="var/chat_style/terminology_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_terminology_dictionary_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-response-total", type=int, default=0)
    parser.add_argument("--min-dictionary-version-presence-ratio", type=float, default=0.0)
    parser.add_argument("--min-normalization-ratio", type=float, default=0.0)
    parser.add_argument("--max-banned-term-violation-total", type=int, default=0)
    parser.add_argument("--max-preferred-term-miss-total", type=int, default=0)
    parser.add_argument("--max-conflict-term-total", type=int, default=0)
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
    summary = summarize_korean_terminology_dictionary_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_response_total=max(0, int(args.min_response_total)),
        min_dictionary_version_presence_ratio=max(0.0, float(args.min_dictionary_version_presence_ratio)),
        min_normalization_ratio=max(0.0, float(args.min_normalization_ratio)),
        max_banned_term_violation_total=max(0, int(args.max_banned_term_violation_total)),
        max_preferred_term_miss_total=max(0, int(args.max_preferred_term_miss_total)),
        max_conflict_term_total=max(0, int(args.max_conflict_term_total)),
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
                "min_response_total": int(args.min_response_total),
                "min_dictionary_version_presence_ratio": float(args.min_dictionary_version_presence_ratio),
                "min_normalization_ratio": float(args.min_normalization_ratio),
                "max_banned_term_violation_total": int(args.max_banned_term_violation_total),
                "max_preferred_term_miss_total": int(args.max_preferred_term_miss_total),
                "max_conflict_term_total": int(args.max_conflict_term_total),
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
    print(f"response_total={_safe_int(summary.get('response_total'), 0)}")
    print(f"banned_term_violation_total={_safe_int(summary.get('banned_term_violation_total'), 0)}")
    print(f"normalization_ratio={_safe_float(summary.get('normalization_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
