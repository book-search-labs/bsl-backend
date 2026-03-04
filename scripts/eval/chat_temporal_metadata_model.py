#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_TIMEZONE = "ASIA/SEOUL"


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items()}


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
    for key in ("updated_at", "created_at", "ingested_at", "timestamp", "generated_at"):
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


def summarize_temporal_metadata(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    doc_total = 0
    missing_source_id_total = 0
    missing_effective_from_total = 0
    missing_announced_at_total = 0
    missing_timezone_total = 0
    invalid_window_total = 0
    open_ended_total = 0
    overlap_conflict_total = 0
    timezone_distribution: dict[str, int] = {}
    windows_by_source: dict[str, list[tuple[datetime, datetime | None]]] = {}

    for row in rows:
        doc_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        source_id = str(row.get("source_id") or row.get("policy_id") or row.get("doc_id") or "").strip()
        if not source_id:
            missing_source_id_total += 1
            source_id = "__missing__"

        effective_from = _parse_ts(row.get("effective_from"))
        effective_to = _parse_ts(row.get("effective_to"))
        announced_at = _parse_ts(row.get("announced_at"))
        timezone_text = str(row.get("timezone") or "").strip()

        if effective_from is None:
            missing_effective_from_total += 1
        if announced_at is None:
            missing_announced_at_total += 1
        if not timezone_text:
            missing_timezone_total += 1
            timezone_text = DEFAULT_TIMEZONE
        timezone_key = timezone_text.upper()
        timezone_distribution[timezone_key] = timezone_distribution.get(timezone_key, 0) + 1

        if effective_from is not None and effective_to is None:
            open_ended_total += 1
        if effective_from is not None and effective_to is not None and effective_to < effective_from:
            invalid_window_total += 1

        if effective_from is not None:
            windows_by_source.setdefault(source_id, []).append((effective_from, effective_to))

    for source_windows in windows_by_source.values():
        ordered = sorted(source_windows, key=lambda item: item[0])
        for idx in range(1, len(ordered)):
            prev_start, prev_end = ordered[idx - 1]
            curr_start, _ = ordered[idx]
            prev_end_cmp = prev_end or datetime.max.replace(tzinfo=timezone.utc)
            if curr_start <= prev_end_cmp:
                overlap_conflict_total += 1

    stale_hours = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 3600.0)

    return {
        "window_size": len(rows),
        "doc_total": doc_total,
        "missing_source_id_total": missing_source_id_total,
        "missing_effective_from_total": missing_effective_from_total,
        "missing_announced_at_total": missing_announced_at_total,
        "missing_timezone_total": missing_timezone_total,
        "invalid_window_total": invalid_window_total,
        "open_ended_total": open_ended_total,
        "overlap_conflict_total": overlap_conflict_total,
        "timezone_distribution": [
            {"timezone": key, "count": value} for key, value in sorted(timezone_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_hours": stale_hours,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_doc_total: int,
    max_missing_source_id_total: int,
    max_missing_effective_from_total: int,
    max_missing_announced_at_total: int,
    max_missing_timezone_total: int,
    max_invalid_window_total: int,
    max_overlap_conflict_total: int,
    max_stale_hours: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    doc_total = _safe_int(summary.get("doc_total"), 0)
    missing_source_id_total = _safe_int(summary.get("missing_source_id_total"), 0)
    missing_effective_from_total = _safe_int(summary.get("missing_effective_from_total"), 0)
    missing_announced_at_total = _safe_int(summary.get("missing_announced_at_total"), 0)
    missing_timezone_total = _safe_int(summary.get("missing_timezone_total"), 0)
    invalid_window_total = _safe_int(summary.get("invalid_window_total"), 0)
    overlap_conflict_total = _safe_int(summary.get("overlap_conflict_total"), 0)
    stale_hours = _safe_float(summary.get("stale_hours"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat temporal metadata window too small: {window_size} < {int(min_window)}")
    if doc_total < max(0, int(min_doc_total)):
        failures.append(f"chat temporal metadata doc total too small: {doc_total} < {int(min_doc_total)}")
    if window_size == 0:
        return failures

    if missing_source_id_total > max(0, int(max_missing_source_id_total)):
        failures.append(
            f"chat temporal metadata missing source id total exceeded: {missing_source_id_total} > {int(max_missing_source_id_total)}"
        )
    if missing_effective_from_total > max(0, int(max_missing_effective_from_total)):
        failures.append(
            "chat temporal metadata missing effective_from total exceeded: "
            f"{missing_effective_from_total} > {int(max_missing_effective_from_total)}"
        )
    if missing_announced_at_total > max(0, int(max_missing_announced_at_total)):
        failures.append(
            "chat temporal metadata missing announced_at total exceeded: "
            f"{missing_announced_at_total} > {int(max_missing_announced_at_total)}"
        )
    if missing_timezone_total > max(0, int(max_missing_timezone_total)):
        failures.append(
            f"chat temporal metadata missing timezone total exceeded: {missing_timezone_total} > {int(max_missing_timezone_total)}"
        )
    if invalid_window_total > max(0, int(max_invalid_window_total)):
        failures.append(
            f"chat temporal metadata invalid window total exceeded: {invalid_window_total} > {int(max_invalid_window_total)}"
        )
    if overlap_conflict_total > max(0, int(max_overlap_conflict_total)):
        failures.append(
            f"chat temporal metadata overlap conflict total exceeded: {overlap_conflict_total} > {int(max_overlap_conflict_total)}"
        )
    if stale_hours > max(0.0, float(max_stale_hours)):
        failures.append(f"chat temporal metadata stale: {stale_hours:.2f}h > {float(max_stale_hours):.2f}h")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_doc_total_drop: int,
    max_missing_source_id_total_increase: int,
    max_missing_effective_from_total_increase: int,
    max_missing_announced_at_total_increase: int,
    max_missing_timezone_total_increase: int,
    max_invalid_window_total_increase: int,
    max_overlap_conflict_total_increase: int,
    max_stale_hours_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_doc_total = _safe_int(base_summary.get("doc_total"), 0)
    cur_doc_total = _safe_int(current_summary.get("doc_total"), 0)
    doc_total_drop = max(0, base_doc_total - cur_doc_total)
    if doc_total_drop > max(0, int(max_doc_total_drop)):
        failures.append(
            f"doc_total regression: baseline={base_doc_total}, current={cur_doc_total}, "
            f"allowed_drop={max(0, int(max_doc_total_drop))}"
        )

    baseline_increase_pairs = [
        ("missing_source_id_total", max_missing_source_id_total_increase),
        ("missing_effective_from_total", max_missing_effective_from_total_increase),
        ("missing_announced_at_total", max_missing_announced_at_total_increase),
        ("missing_timezone_total", max_missing_timezone_total_increase),
        ("invalid_window_total", max_invalid_window_total_increase),
        ("overlap_conflict_total", max_overlap_conflict_total_increase),
    ]
    for key, allowed_increase in baseline_increase_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_stale_hours = _safe_float(base_summary.get("stale_hours"), 0.0)
    cur_stale_hours = _safe_float(current_summary.get("stale_hours"), 0.0)
    stale_hours_increase = max(0.0, cur_stale_hours - base_stale_hours)
    if stale_hours_increase > max(0.0, float(max_stale_hours_increase)):
        failures.append(
            "stale hours regression: "
            f"baseline={base_stale_hours:.6f}, current={cur_stale_hours:.6f}, "
            f"allowed_increase={float(max_stale_hours_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Temporal Metadata Model")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- doc_total: {_safe_int(summary.get('doc_total'), 0)}")
    lines.append(f"- missing_effective_from_total: {_safe_int(summary.get('missing_effective_from_total'), 0)}")
    lines.append(f"- invalid_window_total: {_safe_int(summary.get('invalid_window_total'), 0)}")
    lines.append(f"- overlap_conflict_total: {_safe_int(summary.get('overlap_conflict_total'), 0)}")
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
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat temporal metadata model quality.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/temporal_meta.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_temporal_metadata_model")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-doc-total", type=int, default=0)
    parser.add_argument("--max-missing-source-id-total", type=int, default=0)
    parser.add_argument("--max-missing-effective-from-total", type=int, default=0)
    parser.add_argument("--max-missing-announced-at-total", type=int, default=0)
    parser.add_argument("--max-missing-timezone-total", type=int, default=0)
    parser.add_argument("--max-invalid-window-total", type=int, default=0)
    parser.add_argument("--max-overlap-conflict-total", type=int, default=0)
    parser.add_argument("--max-stale-hours", type=float, default=24.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-doc-total-drop", type=int, default=10)
    parser.add_argument("--max-missing-source-id-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-effective-from-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-announced-at-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-timezone-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-window-total-increase", type=int, default=0)
    parser.add_argument("--max-overlap-conflict-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-hours-increase", type=float, default=24.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_temporal_metadata(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_doc_total=max(0, int(args.min_doc_total)),
        max_missing_source_id_total=max(0, int(args.max_missing_source_id_total)),
        max_missing_effective_from_total=max(0, int(args.max_missing_effective_from_total)),
        max_missing_announced_at_total=max(0, int(args.max_missing_announced_at_total)),
        max_missing_timezone_total=max(0, int(args.max_missing_timezone_total)),
        max_invalid_window_total=max(0, int(args.max_invalid_window_total)),
        max_overlap_conflict_total=max(0, int(args.max_overlap_conflict_total)),
        max_stale_hours=max(0.0, float(args.max_stale_hours)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_doc_total_drop=max(0, int(args.max_doc_total_drop)),
            max_missing_source_id_total_increase=max(0, int(args.max_missing_source_id_total_increase)),
            max_missing_effective_from_total_increase=max(0, int(args.max_missing_effective_from_total_increase)),
            max_missing_announced_at_total_increase=max(0, int(args.max_missing_announced_at_total_increase)),
            max_missing_timezone_total_increase=max(0, int(args.max_missing_timezone_total_increase)),
            max_invalid_window_total_increase=max(0, int(args.max_invalid_window_total_increase)),
            max_overlap_conflict_total_increase=max(0, int(args.max_overlap_conflict_total_increase)),
            max_stale_hours_increase=max(0.0, float(args.max_stale_hours_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "source": {
            "events_jsonl": str(args.events_jsonl),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
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
                "min_doc_total": int(args.min_doc_total),
                "max_missing_source_id_total": int(args.max_missing_source_id_total),
                "max_missing_effective_from_total": int(args.max_missing_effective_from_total),
                "max_missing_announced_at_total": int(args.max_missing_announced_at_total),
                "max_missing_timezone_total": int(args.max_missing_timezone_total),
                "max_invalid_window_total": int(args.max_invalid_window_total),
                "max_overlap_conflict_total": int(args.max_overlap_conflict_total),
                "max_stale_hours": float(args.max_stale_hours),
                "max_doc_total_drop": int(args.max_doc_total_drop),
                "max_missing_source_id_total_increase": int(args.max_missing_source_id_total_increase),
                "max_missing_effective_from_total_increase": int(args.max_missing_effective_from_total_increase),
                "max_missing_announced_at_total_increase": int(args.max_missing_announced_at_total_increase),
                "max_missing_timezone_total_increase": int(args.max_missing_timezone_total_increase),
                "max_invalid_window_total_increase": int(args.max_invalid_window_total_increase),
                "max_overlap_conflict_total_increase": int(args.max_overlap_conflict_total_increase),
                "max_stale_hours_increase": float(args.max_stale_hours_increase),
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
    print(f"doc_total={_safe_int(summary.get('doc_total'), 0)}")
    print(f"invalid_window_total={_safe_int(summary.get('invalid_window_total'), 0)}")
    print(f"overlap_conflict_total={_safe_int(summary.get('overlap_conflict_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
