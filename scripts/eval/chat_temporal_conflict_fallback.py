#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SAFE_DECISIONS = {"ABSTAIN", "ASK", "ESCALATE", "HUMAN_HANDOFF", "DEFER", "FALLBACK"}
UNSAFE_DECISIONS = {"ANSWER", "EXECUTE", "PROCEED"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "resolved_at", "generated_at"):
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


def _decision(row: Mapping[str, Any]) -> str:
    text = str(row.get("decision") or row.get("route") or row.get("action") or "").strip().upper()
    aliases = {"HANDOFF": "HUMAN_HANDOFF", "DISAMBIGUATE": "ASK", "SAFE_FALLBACK": "FALLBACK"}
    return aliases.get(text, text or "UNKNOWN")


def _source_links(row: Mapping[str, Any]) -> list[str]:
    links = row.get("source_links") or row.get("citations")
    if isinstance(links, list):
        return [str(item or "").strip() for item in links if str(item or "").strip()]
    if isinstance(links, str):
        return [links.strip()] if links.strip() else []
    return []


def _is_temporal_conflict(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("temporal_conflict"), False) or _safe_bool(row.get("conflict_detected"), False):
        return True
    conflict_type = str(row.get("conflict_type") or "").strip().upper()
    return conflict_type in {"TEMPORAL", "EFFECTIVE_DATE", "DATE_CONFLICT", "VERSION_WINDOW"}


def _requires_fallback(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("requires_fallback"), False):
        return True
    if _safe_bool(row.get("time_ambiguous"), False) or _safe_bool(row.get("unresolved"), False):
        return True
    status = str(row.get("resolution_status") or row.get("status") or "").strip().upper()
    return status in {"UNRESOLVED", "CONFLICTED", "PENDING_CONFIRMATION"}


def _is_safe_fallback(row: Mapping[str, Any], decision: str) -> bool:
    if _safe_bool(row.get("safe_fallback_used"), False) or _safe_bool(row.get("abstained"), False):
        return True
    return decision in SAFE_DECISIONS


def _has_followup_prompt(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("followup_asked"), False):
        return True
    text = str(row.get("assistant_message") or row.get("response_text") or "").lower()
    return "기준일" in text or "어느 날짜" in text or "which date" in text or "reference date" in text


def _fallback_latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("fallback_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("fallback_latency_seconds")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_temporal_conflict_fallback(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    temporal_conflict_total = 0
    fallback_expected_total = 0
    safe_fallback_total = 0
    unsafe_resolution_total = 0
    missing_followup_prompt_total = 0
    missing_official_source_link_total = 0
    missing_reason_code_total = 0
    latency_samples: list[float] = []

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _is_temporal_conflict(row):
            continue
        temporal_conflict_total += 1

        if not _requires_fallback(row):
            continue
        fallback_expected_total += 1

        decision = _decision(row)
        safe_fallback = _is_safe_fallback(row, decision)
        if safe_fallback:
            safe_fallback_total += 1

        definitive_claim = _safe_bool(row.get("definitive_claim"), False)
        if decision in UNSAFE_DECISIONS or definitive_claim:
            unsafe_resolution_total += 1

        if not _has_followup_prompt(row):
            missing_followup_prompt_total += 1
        if not _source_links(row):
            missing_official_source_link_total += 1
        if not str(row.get("reason_code") or "").strip():
            missing_reason_code_total += 1

        latency_samples.append(_fallback_latency_ms(row))

    fallback_coverage_ratio = 1.0 if fallback_expected_total == 0 else float(safe_fallback_total) / float(
        fallback_expected_total
    )
    p95_fallback_latency_ms = _p95(latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "temporal_conflict_total": temporal_conflict_total,
        "fallback_expected_total": fallback_expected_total,
        "safe_fallback_total": safe_fallback_total,
        "fallback_coverage_ratio": fallback_coverage_ratio,
        "unsafe_resolution_total": unsafe_resolution_total,
        "missing_followup_prompt_total": missing_followup_prompt_total,
        "missing_official_source_link_total": missing_official_source_link_total,
        "missing_reason_code_total": missing_reason_code_total,
        "p95_fallback_latency_ms": p95_fallback_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_temporal_conflict_total: int,
    min_fallback_coverage_ratio: float,
    max_unsafe_resolution_total: int,
    max_missing_followup_prompt_total: int,
    max_missing_official_source_link_total: int,
    max_missing_reason_code_total: int,
    max_p95_fallback_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    temporal_conflict_total = _safe_int(summary.get("temporal_conflict_total"), 0)
    fallback_coverage_ratio = _safe_float(summary.get("fallback_coverage_ratio"), 1.0)
    unsafe_resolution_total = _safe_int(summary.get("unsafe_resolution_total"), 0)
    missing_followup_prompt_total = _safe_int(summary.get("missing_followup_prompt_total"), 0)
    missing_official_source_link_total = _safe_int(summary.get("missing_official_source_link_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    p95_fallback_latency_ms = _safe_float(summary.get("p95_fallback_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat temporal conflict fallback window too small: {window_size} < {int(min_window)}")
    if temporal_conflict_total < max(0, int(min_temporal_conflict_total)):
        failures.append(
            "chat temporal conflict total too small: "
            f"{temporal_conflict_total} < {int(min_temporal_conflict_total)}"
        )
    if window_size == 0:
        return failures

    if fallback_coverage_ratio < max(0.0, float(min_fallback_coverage_ratio)):
        failures.append(
            "chat temporal fallback coverage ratio below minimum: "
            f"{fallback_coverage_ratio:.4f} < {float(min_fallback_coverage_ratio):.4f}"
        )
    if unsafe_resolution_total > max(0, int(max_unsafe_resolution_total)):
        failures.append(
            f"chat temporal unsafe resolution total exceeded: {unsafe_resolution_total} > {int(max_unsafe_resolution_total)}"
        )
    if missing_followup_prompt_total > max(0, int(max_missing_followup_prompt_total)):
        failures.append(
            "chat temporal missing follow-up prompt total exceeded: "
            f"{missing_followup_prompt_total} > {int(max_missing_followup_prompt_total)}"
        )
    if missing_official_source_link_total > max(0, int(max_missing_official_source_link_total)):
        failures.append(
            "chat temporal missing official source link total exceeded: "
            f"{missing_official_source_link_total} > {int(max_missing_official_source_link_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"chat temporal missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if p95_fallback_latency_ms > max(0.0, float(max_p95_fallback_latency_ms)):
        failures.append(
            f"chat temporal fallback p95 latency exceeded: {p95_fallback_latency_ms:.2f}ms > {float(max_p95_fallback_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat temporal conflict fallback stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_temporal_conflict_total_drop: int,
    max_fallback_expected_total_drop: int,
    max_safe_fallback_total_drop: int,
    max_fallback_coverage_ratio_drop: float,
    max_unsafe_resolution_total_increase: int,
    max_missing_followup_prompt_total_increase: int,
    max_missing_official_source_link_total_increase: int,
    max_missing_reason_code_total_increase: int,
    max_p95_fallback_latency_ms_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("temporal_conflict_total", max_temporal_conflict_total_drop),
        ("fallback_expected_total", max_fallback_expected_total_drop),
        ("safe_fallback_total", max_safe_fallback_total_drop),
    ]
    for key, allowed_drop in baseline_drop_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    base_fallback_coverage_ratio = _safe_float(base_summary.get("fallback_coverage_ratio"), 1.0)
    cur_fallback_coverage_ratio = _safe_float(current_summary.get("fallback_coverage_ratio"), 1.0)
    fallback_coverage_ratio_drop = max(0.0, base_fallback_coverage_ratio - cur_fallback_coverage_ratio)
    if fallback_coverage_ratio_drop > max(0.0, float(max_fallback_coverage_ratio_drop)):
        failures.append(
            "fallback_coverage_ratio regression: "
            f"baseline={base_fallback_coverage_ratio:.6f}, current={cur_fallback_coverage_ratio:.6f}, "
            f"allowed_drop={float(max_fallback_coverage_ratio_drop):.6f}"
        )

    baseline_increase_pairs = [
        ("unsafe_resolution_total", max_unsafe_resolution_total_increase),
        ("missing_followup_prompt_total", max_missing_followup_prompt_total_increase),
        ("missing_official_source_link_total", max_missing_official_source_link_total_increase),
        ("missing_reason_code_total", max_missing_reason_code_total_increase),
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

    base_p95_fallback_latency_ms = _safe_float(base_summary.get("p95_fallback_latency_ms"), 0.0)
    cur_p95_fallback_latency_ms = _safe_float(current_summary.get("p95_fallback_latency_ms"), 0.0)
    p95_fallback_latency_ms_increase = max(0.0, cur_p95_fallback_latency_ms - base_p95_fallback_latency_ms)
    if p95_fallback_latency_ms_increase > max(0.0, float(max_p95_fallback_latency_ms_increase)):
        failures.append(
            "p95_fallback_latency_ms regression: "
            f"baseline={base_p95_fallback_latency_ms:.6f}, current={cur_p95_fallback_latency_ms:.6f}, "
            f"allowed_increase={float(max_p95_fallback_latency_ms_increase):.6f}"
        )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Temporal Conflict Fallback")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- temporal_conflict_total: {_safe_int(summary.get('temporal_conflict_total'), 0)}")
    lines.append(f"- fallback_expected_total: {_safe_int(summary.get('fallback_expected_total'), 0)}")
    lines.append(f"- fallback_coverage_ratio: {_safe_float(summary.get('fallback_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- unsafe_resolution_total: {_safe_int(summary.get('unsafe_resolution_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate temporal conflict fallback handling.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/temporal_conflict_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_temporal_conflict_fallback")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-temporal-conflict-total", type=int, default=0)
    parser.add_argument("--min-fallback-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-unsafe-resolution-total", type=int, default=0)
    parser.add_argument("--max-missing-followup-prompt-total", type=int, default=0)
    parser.add_argument("--max-missing-official-source-link-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-p95-fallback-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-temporal-conflict-total-drop", type=int, default=10)
    parser.add_argument("--max-fallback-expected-total-drop", type=int, default=10)
    parser.add_argument("--max-safe-fallback-total-drop", type=int, default=10)
    parser.add_argument("--max-fallback-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-unsafe-resolution-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-followup-prompt-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-official-source-link-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-fallback-latency-ms-increase", type=float, default=100.0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_temporal_conflict_fallback(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_temporal_conflict_total=max(0, int(args.min_temporal_conflict_total)),
        min_fallback_coverage_ratio=max(0.0, float(args.min_fallback_coverage_ratio)),
        max_unsafe_resolution_total=max(0, int(args.max_unsafe_resolution_total)),
        max_missing_followup_prompt_total=max(0, int(args.max_missing_followup_prompt_total)),
        max_missing_official_source_link_total=max(0, int(args.max_missing_official_source_link_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_p95_fallback_latency_ms=max(0.0, float(args.max_p95_fallback_latency_ms)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_temporal_conflict_total_drop=max(0, int(args.max_temporal_conflict_total_drop)),
            max_fallback_expected_total_drop=max(0, int(args.max_fallback_expected_total_drop)),
            max_safe_fallback_total_drop=max(0, int(args.max_safe_fallback_total_drop)),
            max_fallback_coverage_ratio_drop=max(0.0, float(args.max_fallback_coverage_ratio_drop)),
            max_unsafe_resolution_total_increase=max(0, int(args.max_unsafe_resolution_total_increase)),
            max_missing_followup_prompt_total_increase=max(0, int(args.max_missing_followup_prompt_total_increase)),
            max_missing_official_source_link_total_increase=max(
                0, int(args.max_missing_official_source_link_total_increase)
            ),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_p95_fallback_latency_ms_increase=max(0.0, float(args.max_p95_fallback_latency_ms_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
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
                "min_temporal_conflict_total": int(args.min_temporal_conflict_total),
                "min_fallback_coverage_ratio": float(args.min_fallback_coverage_ratio),
                "max_unsafe_resolution_total": int(args.max_unsafe_resolution_total),
                "max_missing_followup_prompt_total": int(args.max_missing_followup_prompt_total),
                "max_missing_official_source_link_total": int(args.max_missing_official_source_link_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_p95_fallback_latency_ms": float(args.max_p95_fallback_latency_ms),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_temporal_conflict_total_drop": int(args.max_temporal_conflict_total_drop),
                "max_fallback_expected_total_drop": int(args.max_fallback_expected_total_drop),
                "max_safe_fallback_total_drop": int(args.max_safe_fallback_total_drop),
                "max_fallback_coverage_ratio_drop": float(args.max_fallback_coverage_ratio_drop),
                "max_unsafe_resolution_total_increase": int(args.max_unsafe_resolution_total_increase),
                "max_missing_followup_prompt_total_increase": int(args.max_missing_followup_prompt_total_increase),
                "max_missing_official_source_link_total_increase": int(args.max_missing_official_source_link_total_increase),
                "max_missing_reason_code_total_increase": int(args.max_missing_reason_code_total_increase),
                "max_p95_fallback_latency_ms_increase": float(args.max_p95_fallback_latency_ms_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"temporal_conflict_total={_safe_int(summary.get('temporal_conflict_total'), 0)}")
    print(f"unsafe_resolution_total={_safe_int(summary.get('unsafe_resolution_total'), 0)}")
    print(f"missing_official_source_link_total={_safe_int(summary.get('missing_official_source_link_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
