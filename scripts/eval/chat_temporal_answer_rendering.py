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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "answered_at", "generated_at"):
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


def _has_effective_date(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("has_effective_date"), False):
        return True
    text = str(row.get("answer_text") or row.get("assistant_message") or "").lower()
    markers = ("effective", "적용일", "기준일", "from", "to")
    return any(marker in text for marker in markers)


def _has_policy_version(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("has_policy_version"), False):
        return True
    if str(row.get("policy_version") or "").strip():
        return True
    text = str(row.get("answer_text") or row.get("assistant_message") or "").lower()
    return "v" in text and "policy" in text


def _has_reference_date(row: Mapping[str, Any]) -> bool:
    if str(row.get("reference_date") or row.get("reference_time") or "").strip():
        return True
    return _safe_bool(row.get("has_reference_date"), False)


def _is_ambiguous_query(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("time_ambiguous"), False) or _safe_bool(row.get("ambiguous_query"), False)


def _asked_followup(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("followup_asked"), False):
        return True
    route = str(row.get("route") or "").strip().upper()
    if route in {"ASK", "DISAMBIGUATE"}:
        return True
    text = str(row.get("answer_text") or row.get("assistant_message") or "").lower()
    return "어느" in text or "기준" in text or "which date" in text or "reference time" in text


def _has_official_source_link(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("has_official_source_link"), False):
        return True
    links = row.get("source_links") or row.get("citations")
    if isinstance(links, list):
        for link in links:
            text = str(link or "").lower()
            if "official" in text or "policy" in text or "gov" in text or "book-search-labs" in text:
                return True
    text = str(row.get("answer_text") or row.get("assistant_message") or "").lower()
    return "http" in text and ("official" in text or "policy" in text)


def _render_latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("render_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("render_latency_seconds")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_temporal_answer_rendering(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    answer_total = 0
    with_effective_date_total = 0
    with_policy_version_total = 0
    missing_reference_date_total = 0
    ambiguous_query_total = 0
    ambiguous_followup_total = 0
    ambiguous_direct_answer_total = 0
    missing_official_source_link_total = 0
    render_contract_violation_total = 0
    latency_samples: list[float] = []

    for row in rows:
        answer_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        has_effective_date = _has_effective_date(row)
        has_policy_version = _has_policy_version(row)
        has_reference_date = _has_reference_date(row)
        has_source_link = _has_official_source_link(row)

        if has_effective_date:
            with_effective_date_total += 1
        if has_policy_version:
            with_policy_version_total += 1
        if not has_reference_date:
            missing_reference_date_total += 1
        if not has_source_link:
            missing_official_source_link_total += 1

        ambiguous = _is_ambiguous_query(row)
        if ambiguous:
            ambiguous_query_total += 1
            if _asked_followup(row):
                ambiguous_followup_total += 1
            else:
                ambiguous_direct_answer_total += 1

        if not has_effective_date or not has_policy_version or not has_reference_date:
            render_contract_violation_total += 1

        latency_samples.append(_render_latency_ms(row))

    effective_date_ratio = 1.0 if answer_total == 0 else float(with_effective_date_total) / float(answer_total)
    policy_version_ratio = 1.0 if answer_total == 0 else float(with_policy_version_total) / float(answer_total)
    ambiguous_followup_ratio = (
        1.0 if ambiguous_query_total == 0 else float(ambiguous_followup_total) / float(ambiguous_query_total)
    )
    p95_render_latency_ms = _p95(latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "answer_total": answer_total,
        "with_effective_date_total": with_effective_date_total,
        "with_policy_version_total": with_policy_version_total,
        "effective_date_ratio": effective_date_ratio,
        "policy_version_ratio": policy_version_ratio,
        "missing_reference_date_total": missing_reference_date_total,
        "ambiguous_query_total": ambiguous_query_total,
        "ambiguous_followup_total": ambiguous_followup_total,
        "ambiguous_followup_ratio": ambiguous_followup_ratio,
        "ambiguous_direct_answer_total": ambiguous_direct_answer_total,
        "missing_official_source_link_total": missing_official_source_link_total,
        "render_contract_violation_total": render_contract_violation_total,
        "p95_render_latency_ms": p95_render_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_answer_total: int,
    min_effective_date_ratio: float,
    min_policy_version_ratio: float,
    min_ambiguous_followup_ratio: float,
    max_missing_reference_date_total: int,
    max_ambiguous_direct_answer_total: int,
    max_missing_official_source_link_total: int,
    max_render_contract_violation_total: int,
    max_p95_render_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    answer_total = _safe_int(summary.get("answer_total"), 0)
    effective_date_ratio = _safe_float(summary.get("effective_date_ratio"), 0.0)
    policy_version_ratio = _safe_float(summary.get("policy_version_ratio"), 0.0)
    ambiguous_followup_ratio = _safe_float(summary.get("ambiguous_followup_ratio"), 0.0)
    missing_reference_date_total = _safe_int(summary.get("missing_reference_date_total"), 0)
    ambiguous_direct_answer_total = _safe_int(summary.get("ambiguous_direct_answer_total"), 0)
    missing_official_source_link_total = _safe_int(summary.get("missing_official_source_link_total"), 0)
    render_contract_violation_total = _safe_int(summary.get("render_contract_violation_total"), 0)
    p95_render_latency_ms = _safe_float(summary.get("p95_render_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat temporal answer rendering window too small: {window_size} < {int(min_window)}")
    if answer_total < max(0, int(min_answer_total)):
        failures.append(f"chat temporal answer total too small: {answer_total} < {int(min_answer_total)}")
    if window_size == 0:
        return failures

    if effective_date_ratio < max(0.0, float(min_effective_date_ratio)):
        failures.append(
            f"chat temporal effective-date ratio below minimum: {effective_date_ratio:.4f} < {float(min_effective_date_ratio):.4f}"
        )
    if policy_version_ratio < max(0.0, float(min_policy_version_ratio)):
        failures.append(
            f"chat temporal policy-version ratio below minimum: {policy_version_ratio:.4f} < {float(min_policy_version_ratio):.4f}"
        )
    if ambiguous_followup_ratio < max(0.0, float(min_ambiguous_followup_ratio)):
        failures.append(
            "chat temporal ambiguous followup ratio below minimum: "
            f"{ambiguous_followup_ratio:.4f} < {float(min_ambiguous_followup_ratio):.4f}"
        )
    if missing_reference_date_total > max(0, int(max_missing_reference_date_total)):
        failures.append(
            f"chat temporal missing reference date total exceeded: {missing_reference_date_total} > {int(max_missing_reference_date_total)}"
        )
    if ambiguous_direct_answer_total > max(0, int(max_ambiguous_direct_answer_total)):
        failures.append(
            f"chat temporal ambiguous direct answer total exceeded: {ambiguous_direct_answer_total} > {int(max_ambiguous_direct_answer_total)}"
        )
    if missing_official_source_link_total > max(0, int(max_missing_official_source_link_total)):
        failures.append(
            "chat temporal missing official source link total exceeded: "
            f"{missing_official_source_link_total} > {int(max_missing_official_source_link_total)}"
        )
    if render_contract_violation_total > max(0, int(max_render_contract_violation_total)):
        failures.append(
            "chat temporal render contract violation total exceeded: "
            f"{render_contract_violation_total} > {int(max_render_contract_violation_total)}"
        )
    if p95_render_latency_ms > max(0.0, float(max_p95_render_latency_ms)):
        failures.append(
            f"chat temporal render p95 latency exceeded: {p95_render_latency_ms:.2f}ms > {float(max_p95_render_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat temporal answer rendering stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_answer_total_drop: int,
    max_with_effective_date_total_drop: int,
    max_with_policy_version_total_drop: int,
    max_effective_date_ratio_drop: float,
    max_policy_version_ratio_drop: float,
    max_ambiguous_followup_ratio_drop: float,
    max_missing_reference_date_total_increase: int,
    max_ambiguous_direct_answer_total_increase: int,
    max_missing_official_source_link_total_increase: int,
    max_render_contract_violation_total_increase: int,
    max_p95_render_latency_ms_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("answer_total", max_answer_total_drop),
        ("with_effective_date_total", max_with_effective_date_total_drop),
        ("with_policy_version_total", max_with_policy_version_total_drop),
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

    baseline_ratio_drop_pairs = [
        ("effective_date_ratio", max_effective_date_ratio_drop),
        ("policy_version_ratio", max_policy_version_ratio_drop),
        ("ambiguous_followup_ratio", max_ambiguous_followup_ratio_drop),
    ]
    for key, allowed_drop in baseline_ratio_drop_pairs:
        base_value = _safe_float(base_summary.get(key), 1.0)
        cur_value = _safe_float(current_summary.get(key), 1.0)
        drop = max(0.0, base_value - cur_value)
        if drop > max(0.0, float(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value:.6f}, current={cur_value:.6f}, "
                f"allowed_drop={float(allowed_drop):.6f}"
            )

    baseline_increase_pairs = [
        ("missing_reference_date_total", max_missing_reference_date_total_increase),
        ("ambiguous_direct_answer_total", max_ambiguous_direct_answer_total_increase),
        ("missing_official_source_link_total", max_missing_official_source_link_total_increase),
        ("render_contract_violation_total", max_render_contract_violation_total_increase),
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

    base_p95_render_latency_ms = _safe_float(base_summary.get("p95_render_latency_ms"), 0.0)
    cur_p95_render_latency_ms = _safe_float(current_summary.get("p95_render_latency_ms"), 0.0)
    p95_render_latency_ms_increase = max(0.0, cur_p95_render_latency_ms - base_p95_render_latency_ms)
    if p95_render_latency_ms_increase > max(0.0, float(max_p95_render_latency_ms_increase)):
        failures.append(
            "p95_render_latency_ms regression: "
            f"baseline={base_p95_render_latency_ms:.6f}, current={cur_p95_render_latency_ms:.6f}, "
            f"allowed_increase={float(max_p95_render_latency_ms_increase):.6f}"
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
    lines.append("# Chat Temporal Answer Rendering")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- answer_total: {_safe_int(summary.get('answer_total'), 0)}")
    lines.append(f"- with_effective_date_total: {_safe_int(summary.get('with_effective_date_total'), 0)}")
    lines.append(f"- with_policy_version_total: {_safe_int(summary.get('with_policy_version_total'), 0)}")
    lines.append(f"- ambiguous_direct_answer_total: {_safe_int(summary.get('ambiguous_direct_answer_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate temporal answer rendering quality.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/temporal_answer_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_temporal_answer_rendering")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-answer-total", type=int, default=0)
    parser.add_argument("--min-effective-date-ratio", type=float, default=0.0)
    parser.add_argument("--min-policy-version-ratio", type=float, default=0.0)
    parser.add_argument("--min-ambiguous-followup-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-reference-date-total", type=int, default=0)
    parser.add_argument("--max-ambiguous-direct-answer-total", type=int, default=0)
    parser.add_argument("--max-missing-official-source-link-total", type=int, default=0)
    parser.add_argument("--max-render-contract-violation-total", type=int, default=0)
    parser.add_argument("--max-p95-render-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-answer-total-drop", type=int, default=10)
    parser.add_argument("--max-with-effective-date-total-drop", type=int, default=10)
    parser.add_argument("--max-with-policy-version-total-drop", type=int, default=10)
    parser.add_argument("--max-effective-date-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-policy-version-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-ambiguous-followup-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-missing-reference-date-total-increase", type=int, default=0)
    parser.add_argument("--max-ambiguous-direct-answer-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-official-source-link-total-increase", type=int, default=0)
    parser.add_argument("--max-render-contract-violation-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-render-latency-ms-increase", type=float, default=100.0)
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
    summary = summarize_temporal_answer_rendering(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_answer_total=max(0, int(args.min_answer_total)),
        min_effective_date_ratio=max(0.0, float(args.min_effective_date_ratio)),
        min_policy_version_ratio=max(0.0, float(args.min_policy_version_ratio)),
        min_ambiguous_followup_ratio=max(0.0, float(args.min_ambiguous_followup_ratio)),
        max_missing_reference_date_total=max(0, int(args.max_missing_reference_date_total)),
        max_ambiguous_direct_answer_total=max(0, int(args.max_ambiguous_direct_answer_total)),
        max_missing_official_source_link_total=max(0, int(args.max_missing_official_source_link_total)),
        max_render_contract_violation_total=max(0, int(args.max_render_contract_violation_total)),
        max_p95_render_latency_ms=max(0.0, float(args.max_p95_render_latency_ms)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_answer_total_drop=max(0, int(args.max_answer_total_drop)),
            max_with_effective_date_total_drop=max(0, int(args.max_with_effective_date_total_drop)),
            max_with_policy_version_total_drop=max(0, int(args.max_with_policy_version_total_drop)),
            max_effective_date_ratio_drop=max(0.0, float(args.max_effective_date_ratio_drop)),
            max_policy_version_ratio_drop=max(0.0, float(args.max_policy_version_ratio_drop)),
            max_ambiguous_followup_ratio_drop=max(0.0, float(args.max_ambiguous_followup_ratio_drop)),
            max_missing_reference_date_total_increase=max(0, int(args.max_missing_reference_date_total_increase)),
            max_ambiguous_direct_answer_total_increase=max(0, int(args.max_ambiguous_direct_answer_total_increase)),
            max_missing_official_source_link_total_increase=max(
                0, int(args.max_missing_official_source_link_total_increase)
            ),
            max_render_contract_violation_total_increase=max(0, int(args.max_render_contract_violation_total_increase)),
            max_p95_render_latency_ms_increase=max(0.0, float(args.max_p95_render_latency_ms_increase)),
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
                "min_answer_total": int(args.min_answer_total),
                "min_effective_date_ratio": float(args.min_effective_date_ratio),
                "min_policy_version_ratio": float(args.min_policy_version_ratio),
                "min_ambiguous_followup_ratio": float(args.min_ambiguous_followup_ratio),
                "max_missing_reference_date_total": int(args.max_missing_reference_date_total),
                "max_ambiguous_direct_answer_total": int(args.max_ambiguous_direct_answer_total),
                "max_missing_official_source_link_total": int(args.max_missing_official_source_link_total),
                "max_render_contract_violation_total": int(args.max_render_contract_violation_total),
                "max_p95_render_latency_ms": float(args.max_p95_render_latency_ms),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_answer_total_drop": int(args.max_answer_total_drop),
                "max_with_effective_date_total_drop": int(args.max_with_effective_date_total_drop),
                "max_with_policy_version_total_drop": int(args.max_with_policy_version_total_drop),
                "max_effective_date_ratio_drop": float(args.max_effective_date_ratio_drop),
                "max_policy_version_ratio_drop": float(args.max_policy_version_ratio_drop),
                "max_ambiguous_followup_ratio_drop": float(args.max_ambiguous_followup_ratio_drop),
                "max_missing_reference_date_total_increase": int(args.max_missing_reference_date_total_increase),
                "max_ambiguous_direct_answer_total_increase": int(args.max_ambiguous_direct_answer_total_increase),
                "max_missing_official_source_link_total_increase": int(args.max_missing_official_source_link_total_increase),
                "max_render_contract_violation_total_increase": int(args.max_render_contract_violation_total_increase),
                "max_p95_render_latency_ms_increase": float(args.max_p95_render_latency_ms_increase),
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
    print(f"answer_total={_safe_int(summary.get('answer_total'), 0)}")
    print(f"ambiguous_direct_answer_total={_safe_int(summary.get('ambiguous_direct_answer_total'), 0)}")
    print(f"render_contract_violation_total={_safe_int(summary.get('render_contract_violation_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
