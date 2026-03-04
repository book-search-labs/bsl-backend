#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

RELATIVE_REFERENCE_TOKENS = {"TODAY", "YESTERDAY", "TOMORROW", "NOW"}
EXPLICIT_REFERENCE_TOKENS = {"DATE", "DATETIME", "ABSOLUTE"}


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


def _reference_time(row: Mapping[str, Any]) -> datetime | None:
    return _parse_ts(row.get("reference_time") or row.get("resolved_reference_time") or row.get("query_time"))


def _reference_type(row: Mapping[str, Any]) -> str:
    text = str(row.get("reference_type") or row.get("time_reference_type") or "").strip().upper()
    aliases = {"RELATIVE": "TODAY", "ABS": "ABSOLUTE", "EXPLICIT_DATE": "DATE"}
    if not text:
        return ""
    return aliases.get(text, text)


def _matched_docs(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    docs = row.get("matched_docs") or row.get("matched_documents") or row.get("results")
    if isinstance(docs, list):
        return [doc for doc in docs if isinstance(doc, Mapping)]
    return []


def _invalid_doc_match_count(reference_time: datetime, docs: list[Mapping[str, Any]]) -> int:
    invalid = 0
    for doc in docs:
        effective_from = _parse_ts(doc.get("effective_from"))
        effective_to = _parse_ts(doc.get("effective_to"))
        if effective_from is not None and reference_time < effective_from:
            invalid += 1
            continue
        if effective_to is not None and reference_time > effective_to:
            invalid += 1
    return invalid


def _resolve_latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("resolve_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("resolve_latency_seconds")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_temporal_query_filtering(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    request_total = 0
    parse_error_total = 0
    relative_reference_total = 0
    explicit_reference_total = 0
    missing_reference_time_total = 0
    matched_request_total = 0
    zero_match_total = 0
    invalid_match_request_total = 0
    invalid_match_doc_total = 0
    conflict_total = 0
    conflict_unhandled_total = 0
    disambiguation_total = 0
    safe_abstention_total = 0
    missing_reference_timezone_total = 0
    latency_samples: list[float] = []

    for row in rows:
        request_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if _safe_bool(row.get("reference_parse_error"), False):
            parse_error_total += 1

        ref_type = _reference_type(row)
        if ref_type in RELATIVE_REFERENCE_TOKENS:
            relative_reference_total += 1
        elif ref_type in EXPLICIT_REFERENCE_TOKENS:
            explicit_reference_total += 1

        timezone_text = str(row.get("reference_timezone") or row.get("timezone") or "").strip()
        if not timezone_text:
            missing_reference_timezone_total += 1

        reference_time = _reference_time(row)
        if reference_time is None:
            missing_reference_time_total += 1

        docs = _matched_docs(row)
        matched_total = _safe_int(row.get("matched_total"), -1)
        if matched_total < 0:
            matched_total = len(docs)

        if matched_total > 0:
            matched_request_total += 1
        else:
            zero_match_total += 1

        if reference_time is not None and docs:
            invalid_docs = _invalid_doc_match_count(reference_time, docs)
            if invalid_docs > 0:
                invalid_match_request_total += 1
                invalid_match_doc_total += invalid_docs
        else:
            explicit_invalid_total = _safe_int(row.get("invalid_match_total"), 0)
            if explicit_invalid_total > 0:
                invalid_match_request_total += 1
                invalid_match_doc_total += explicit_invalid_total

        conflict = _safe_bool(row.get("conflict_detected"), False)
        if conflict:
            conflict_total += 1
        disambiguated = _safe_bool(row.get("disambiguation_asked"), False) or _safe_bool(
            row.get("disambiguation_applied"), False
        )
        if disambiguated:
            disambiguation_total += 1

        safe_abstain = _safe_bool(row.get("safe_abstention"), False) or _safe_bool(row.get("fallback_used"), False)
        if safe_abstain:
            safe_abstention_total += 1
        if conflict and not disambiguated and not safe_abstain:
            conflict_unhandled_total += 1

        latency_samples.append(_resolve_latency_ms(row))

    match_or_safe_ratio = 1.0 if request_total == 0 else float(matched_request_total + safe_abstention_total) / float(request_total)
    p95_resolve_latency_ms = _p95(latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "request_total": request_total,
        "parse_error_total": parse_error_total,
        "relative_reference_total": relative_reference_total,
        "explicit_reference_total": explicit_reference_total,
        "missing_reference_time_total": missing_reference_time_total,
        "missing_reference_timezone_total": missing_reference_timezone_total,
        "matched_request_total": matched_request_total,
        "zero_match_total": zero_match_total,
        "match_or_safe_ratio": match_or_safe_ratio,
        "invalid_match_request_total": invalid_match_request_total,
        "invalid_match_doc_total": invalid_match_doc_total,
        "conflict_total": conflict_total,
        "conflict_unhandled_total": conflict_unhandled_total,
        "disambiguation_total": disambiguation_total,
        "safe_abstention_total": safe_abstention_total,
        "p95_resolve_latency_ms": p95_resolve_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_request_total: int,
    min_match_or_safe_ratio: float,
    max_parse_error_total: int,
    max_missing_reference_time_total: int,
    max_invalid_match_request_total: int,
    max_conflict_unhandled_total: int,
    max_p95_resolve_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    request_total = _safe_int(summary.get("request_total"), 0)
    match_or_safe_ratio = _safe_float(summary.get("match_or_safe_ratio"), 0.0)
    parse_error_total = _safe_int(summary.get("parse_error_total"), 0)
    missing_reference_time_total = _safe_int(summary.get("missing_reference_time_total"), 0)
    invalid_match_request_total = _safe_int(summary.get("invalid_match_request_total"), 0)
    conflict_unhandled_total = _safe_int(summary.get("conflict_unhandled_total"), 0)
    p95_resolve_latency_ms = _safe_float(summary.get("p95_resolve_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat temporal query filtering window too small: {window_size} < {int(min_window)}")
    if request_total < max(0, int(min_request_total)):
        failures.append(f"chat temporal query request total too small: {request_total} < {int(min_request_total)}")
    if window_size == 0:
        return failures

    if match_or_safe_ratio < max(0.0, float(min_match_or_safe_ratio)):
        failures.append(
            f"chat temporal query match-or-safe ratio below minimum: {match_or_safe_ratio:.4f} < {float(min_match_or_safe_ratio):.4f}"
        )
    if parse_error_total > max(0, int(max_parse_error_total)):
        failures.append(f"chat temporal query parse error total exceeded: {parse_error_total} > {int(max_parse_error_total)}")
    if missing_reference_time_total > max(0, int(max_missing_reference_time_total)):
        failures.append(
            "chat temporal query missing reference time total exceeded: "
            f"{missing_reference_time_total} > {int(max_missing_reference_time_total)}"
        )
    if invalid_match_request_total > max(0, int(max_invalid_match_request_total)):
        failures.append(
            "chat temporal query invalid match request total exceeded: "
            f"{invalid_match_request_total} > {int(max_invalid_match_request_total)}"
        )
    if conflict_unhandled_total > max(0, int(max_conflict_unhandled_total)):
        failures.append(
            "chat temporal query conflict unhandled total exceeded: "
            f"{conflict_unhandled_total} > {int(max_conflict_unhandled_total)}"
        )
    if p95_resolve_latency_ms > max(0.0, float(max_p95_resolve_latency_ms)):
        failures.append(
            f"chat temporal query p95 resolve latency exceeded: {p95_resolve_latency_ms:.2f}ms > {float(max_p95_resolve_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat temporal query filtering stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_request_total_drop: int,
    max_matched_request_total_drop: int,
    max_match_or_safe_ratio_drop: float,
    max_parse_error_total_increase: int,
    max_missing_reference_time_total_increase: int,
    max_invalid_match_request_total_increase: int,
    max_conflict_unhandled_total_increase: int,
    max_p95_resolve_latency_ms_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("request_total", max_request_total_drop),
        ("matched_request_total", max_matched_request_total_drop),
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

    base_match_or_safe_ratio = _safe_float(base_summary.get("match_or_safe_ratio"), 1.0)
    cur_match_or_safe_ratio = _safe_float(current_summary.get("match_or_safe_ratio"), 1.0)
    match_or_safe_ratio_drop = max(0.0, base_match_or_safe_ratio - cur_match_or_safe_ratio)
    if match_or_safe_ratio_drop > max(0.0, float(max_match_or_safe_ratio_drop)):
        failures.append(
            "match_or_safe_ratio regression: "
            f"baseline={base_match_or_safe_ratio:.6f}, current={cur_match_or_safe_ratio:.6f}, "
            f"allowed_drop={float(max_match_or_safe_ratio_drop):.6f}"
        )

    baseline_increase_pairs = [
        ("parse_error_total", max_parse_error_total_increase),
        ("missing_reference_time_total", max_missing_reference_time_total_increase),
        ("invalid_match_request_total", max_invalid_match_request_total_increase),
        ("conflict_unhandled_total", max_conflict_unhandled_total_increase),
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

    base_p95_resolve_latency_ms = _safe_float(base_summary.get("p95_resolve_latency_ms"), 0.0)
    cur_p95_resolve_latency_ms = _safe_float(current_summary.get("p95_resolve_latency_ms"), 0.0)
    p95_resolve_latency_ms_increase = max(0.0, cur_p95_resolve_latency_ms - base_p95_resolve_latency_ms)
    if p95_resolve_latency_ms_increase > max(0.0, float(max_p95_resolve_latency_ms_increase)):
        failures.append(
            "p95_resolve_latency_ms regression: "
            f"baseline={base_p95_resolve_latency_ms:.6f}, current={cur_p95_resolve_latency_ms:.6f}, "
            f"allowed_increase={float(max_p95_resolve_latency_ms_increase):.6f}"
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
    lines.append("# Chat Temporal Query Filtering")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- request_total: {_safe_int(summary.get('request_total'), 0)}")
    lines.append(f"- parse_error_total: {_safe_int(summary.get('parse_error_total'), 0)}")
    lines.append(f"- invalid_match_request_total: {_safe_int(summary.get('invalid_match_request_total'), 0)}")
    lines.append(f"- conflict_unhandled_total: {_safe_int(summary.get('conflict_unhandled_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate query-time temporal filtering behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/temporal_resolution_audit.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_temporal_query_filtering")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-request-total", type=int, default=0)
    parser.add_argument("--min-match-or-safe-ratio", type=float, default=0.0)
    parser.add_argument("--max-parse-error-total", type=int, default=0)
    parser.add_argument("--max-missing-reference-time-total", type=int, default=0)
    parser.add_argument("--max-invalid-match-request-total", type=int, default=0)
    parser.add_argument("--max-conflict-unhandled-total", type=int, default=0)
    parser.add_argument("--max-p95-resolve-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-request-total-drop", type=int, default=10)
    parser.add_argument("--max-matched-request-total-drop", type=int, default=10)
    parser.add_argument("--max-match-or-safe-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-parse-error-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reference-time-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-match-request-total-increase", type=int, default=0)
    parser.add_argument("--max-conflict-unhandled-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-resolve-latency-ms-increase", type=float, default=100.0)
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
    summary = summarize_temporal_query_filtering(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_request_total=max(0, int(args.min_request_total)),
        min_match_or_safe_ratio=max(0.0, float(args.min_match_or_safe_ratio)),
        max_parse_error_total=max(0, int(args.max_parse_error_total)),
        max_missing_reference_time_total=max(0, int(args.max_missing_reference_time_total)),
        max_invalid_match_request_total=max(0, int(args.max_invalid_match_request_total)),
        max_conflict_unhandled_total=max(0, int(args.max_conflict_unhandled_total)),
        max_p95_resolve_latency_ms=max(0.0, float(args.max_p95_resolve_latency_ms)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_request_total_drop=max(0, int(args.max_request_total_drop)),
            max_matched_request_total_drop=max(0, int(args.max_matched_request_total_drop)),
            max_match_or_safe_ratio_drop=max(0.0, float(args.max_match_or_safe_ratio_drop)),
            max_parse_error_total_increase=max(0, int(args.max_parse_error_total_increase)),
            max_missing_reference_time_total_increase=max(0, int(args.max_missing_reference_time_total_increase)),
            max_invalid_match_request_total_increase=max(0, int(args.max_invalid_match_request_total_increase)),
            max_conflict_unhandled_total_increase=max(0, int(args.max_conflict_unhandled_total_increase)),
            max_p95_resolve_latency_ms_increase=max(0.0, float(args.max_p95_resolve_latency_ms_increase)),
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
                "min_request_total": int(args.min_request_total),
                "min_match_or_safe_ratio": float(args.min_match_or_safe_ratio),
                "max_parse_error_total": int(args.max_parse_error_total),
                "max_missing_reference_time_total": int(args.max_missing_reference_time_total),
                "max_invalid_match_request_total": int(args.max_invalid_match_request_total),
                "max_conflict_unhandled_total": int(args.max_conflict_unhandled_total),
                "max_p95_resolve_latency_ms": float(args.max_p95_resolve_latency_ms),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_request_total_drop": int(args.max_request_total_drop),
                "max_matched_request_total_drop": int(args.max_matched_request_total_drop),
                "max_match_or_safe_ratio_drop": float(args.max_match_or_safe_ratio_drop),
                "max_parse_error_total_increase": int(args.max_parse_error_total_increase),
                "max_missing_reference_time_total_increase": int(args.max_missing_reference_time_total_increase),
                "max_invalid_match_request_total_increase": int(args.max_invalid_match_request_total_increase),
                "max_conflict_unhandled_total_increase": int(args.max_conflict_unhandled_total_increase),
                "max_p95_resolve_latency_ms_increase": float(args.max_p95_resolve_latency_ms_increase),
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
    print(f"request_total={_safe_int(summary.get('request_total'), 0)}")
    print(f"parse_error_total={_safe_int(summary.get('parse_error_total'), 0)}")
    print(f"invalid_match_request_total={_safe_int(summary.get('invalid_match_request_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
