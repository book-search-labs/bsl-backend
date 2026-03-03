#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


HIGH_RISK_INTENTS = {"REFUND_REQUEST", "CANCEL_ORDER", "PAYMENT_CHANGE", "ADDRESS_CHANGE"}


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


def _bridge_confidence(row: Mapping[str, Any]) -> float:
    for key in ("rewrite_confidence", "bridge_confidence", "translation_confidence"):
        if key in row:
            return max(0.0, min(1.0, _safe_float(row.get(key), 0.0)))
    return 1.0


def _fallback_triggered(row: Mapping[str, Any]) -> bool:
    if "fallback_triggered" in row:
        return _safe_bool(row.get("fallback_triggered"), False)
    return bool(str(row.get("fallback_reason") or "").strip())


def _source_based_response(row: Mapping[str, Any]) -> bool:
    if "source_based_response" in row:
        return _safe_bool(row.get("source_based_response"), False)
    mode = _normalize_token(row.get("response_mode"))
    return mode in {"SOURCE_BASED", "ORIGINAL_LANGUAGE", "ORIGINAL_QUERY"}


def _clarification_asked(row: Mapping[str, Any]) -> bool:
    if "clarification_asked" in row:
        return _safe_bool(row.get("clarification_asked"), False)
    route = _normalize_token(row.get("route") or row.get("next_action"))
    return route in {"CLARIFY", "ASK_CLARIFICATION", "ASK"}


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("fallback_reason") or row.get("reason_code") or "").strip())


def _is_high_risk(row: Mapping[str, Any]) -> bool:
    intent = _normalize_token(row.get("intent") or row.get("predicted_intent"))
    risk = _normalize_token(row.get("risk_level"))
    if risk in {"HIGH", "CRITICAL"}:
        return True
    return intent in HIGH_RISK_INTENTS


def _is_direct_answer(row: Mapping[str, Any]) -> bool:
    mode = _normalize_token(row.get("response_mode") or row.get("answer_mode"))
    if mode:
        return mode in {"DIRECT", "NORMAL", "ANSWER"}
    return _safe_bool(row.get("direct_answer"), False)


def summarize_crosslingual_fallback_policy_guard(
    rows: list[Mapping[str, Any]],
    *,
    low_confidence_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    low_confidence_total = 0
    fallback_triggered_total = 0
    source_based_response_total = 0
    clarification_asked_total = 0
    unsafe_high_risk_no_fallback_total = 0
    direct_answer_without_fallback_total = 0
    reason_missing_total = 0
    reason_counts: dict[str, int] = {}

    threshold = max(0.0, min(1.0, float(low_confidence_threshold)))
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        low_conf = _bridge_confidence(row) < threshold
        fallback = _fallback_triggered(row)
        source_based = _source_based_response(row)
        clarification = _clarification_asked(row)
        high_risk = _is_high_risk(row)

        if low_conf:
            low_confidence_total += 1
            if fallback:
                fallback_triggered_total += 1
            if not fallback and _is_direct_answer(row):
                direct_answer_without_fallback_total += 1
            if high_risk and not fallback:
                unsafe_high_risk_no_fallback_total += 1

        if fallback:
            if source_based:
                source_based_response_total += 1
            if clarification:
                clarification_asked_total += 1
            reason = str(row.get("fallback_reason") or row.get("reason_code") or "").strip()
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            else:
                reason_missing_total += 1

    fallback_coverage_ratio = 1.0 if low_confidence_total == 0 else float(fallback_triggered_total) / float(low_confidence_total)
    source_based_response_ratio = (
        1.0 if fallback_triggered_total == 0 else float(source_based_response_total) / float(fallback_triggered_total)
    )
    clarification_ratio = (
        1.0 if fallback_triggered_total == 0 else float(clarification_asked_total) / float(fallback_triggered_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "low_confidence_total": low_confidence_total,
        "fallback_triggered_total": fallback_triggered_total,
        "fallback_coverage_ratio": fallback_coverage_ratio,
        "source_based_response_total": source_based_response_total,
        "source_based_response_ratio": source_based_response_ratio,
        "clarification_asked_total": clarification_asked_total,
        "clarification_ratio": clarification_ratio,
        "unsafe_high_risk_no_fallback_total": unsafe_high_risk_no_fallback_total,
        "direct_answer_without_fallback_total": direct_answer_without_fallback_total,
        "reason_missing_total": reason_missing_total,
        "fallback_reason_distribution": [
            {"reason": key, "count": value} for key, value in sorted(reason_counts.items(), key=lambda item: item[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_fallback_coverage_ratio: float,
    min_source_based_response_ratio: float,
    min_clarification_ratio: float,
    max_unsafe_high_risk_no_fallback_total: int,
    max_direct_answer_without_fallback_total: int,
    max_reason_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    fallback_coverage_ratio = _safe_float(summary.get("fallback_coverage_ratio"), 0.0)
    source_based_response_ratio = _safe_float(summary.get("source_based_response_ratio"), 0.0)
    clarification_ratio = _safe_float(summary.get("clarification_ratio"), 0.0)
    unsafe_high_risk_no_fallback_total = _safe_int(summary.get("unsafe_high_risk_no_fallback_total"), 0)
    direct_answer_without_fallback_total = _safe_int(summary.get("direct_answer_without_fallback_total"), 0)
    reason_missing_total = _safe_int(summary.get("reason_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"crosslingual fallback window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"crosslingual fallback event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if fallback_coverage_ratio < max(0.0, float(min_fallback_coverage_ratio)):
        failures.append(
            f"crosslingual fallback coverage ratio below minimum: {fallback_coverage_ratio:.4f} < {float(min_fallback_coverage_ratio):.4f}"
        )
    if source_based_response_ratio < max(0.0, float(min_source_based_response_ratio)):
        failures.append(
            "crosslingual fallback source-based response ratio below minimum: "
            f"{source_based_response_ratio:.4f} < {float(min_source_based_response_ratio):.4f}"
        )
    if clarification_ratio < max(0.0, float(min_clarification_ratio)):
        failures.append(
            f"crosslingual fallback clarification ratio below minimum: {clarification_ratio:.4f} < {float(min_clarification_ratio):.4f}"
        )
    if unsafe_high_risk_no_fallback_total > max(0, int(max_unsafe_high_risk_no_fallback_total)):
        failures.append(
            "crosslingual fallback unsafe high-risk no-fallback total exceeded: "
            f"{unsafe_high_risk_no_fallback_total} > {int(max_unsafe_high_risk_no_fallback_total)}"
        )
    if direct_answer_without_fallback_total > max(0, int(max_direct_answer_without_fallback_total)):
        failures.append(
            "crosslingual fallback direct answer without fallback total exceeded: "
            f"{direct_answer_without_fallback_total} > {int(max_direct_answer_without_fallback_total)}"
        )
    if reason_missing_total > max(0, int(max_reason_missing_total)):
        failures.append(f"crosslingual fallback reason missing total exceeded: {reason_missing_total} > {int(max_reason_missing_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"crosslingual fallback stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Cross-lingual Fallback Policy Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- fallback_coverage_ratio: {_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- source_based_response_ratio: {_safe_float(summary.get('source_based_response_ratio'), 0.0):.4f}")
    lines.append(f"- clarification_ratio: {_safe_float(summary.get('clarification_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate cross-lingual fallback policy for low-confidence rewrites.")
    parser.add_argument("--events-jsonl", default="var/crosslingual/fallback_policy_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_crosslingual_fallback_policy_guard")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.6)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-fallback-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-source-based-response-ratio", type=float, default=0.0)
    parser.add_argument("--min-clarification-ratio", type=float, default=0.0)
    parser.add_argument("--max-unsafe-high-risk-no-fallback-total", type=int, default=1000000)
    parser.add_argument("--max-direct-answer-without-fallback-total", type=int, default=1000000)
    parser.add_argument("--max-reason-missing-total", type=int, default=1000000)
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
    summary = summarize_crosslingual_fallback_policy_guard(
        rows,
        low_confidence_threshold=max(0.0, min(1.0, float(args.low_confidence_threshold))),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_fallback_coverage_ratio=max(0.0, float(args.min_fallback_coverage_ratio)),
        min_source_based_response_ratio=max(0.0, float(args.min_source_based_response_ratio)),
        min_clarification_ratio=max(0.0, float(args.min_clarification_ratio)),
        max_unsafe_high_risk_no_fallback_total=max(0, int(args.max_unsafe_high_risk_no_fallback_total)),
        max_direct_answer_without_fallback_total=max(0, int(args.max_direct_answer_without_fallback_total)),
        max_reason_missing_total=max(0, int(args.max_reason_missing_total)),
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
                "low_confidence_threshold": float(args.low_confidence_threshold),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_fallback_coverage_ratio": float(args.min_fallback_coverage_ratio),
                "min_source_based_response_ratio": float(args.min_source_based_response_ratio),
                "min_clarification_ratio": float(args.min_clarification_ratio),
                "max_unsafe_high_risk_no_fallback_total": int(args.max_unsafe_high_risk_no_fallback_total),
                "max_direct_answer_without_fallback_total": int(args.max_direct_answer_without_fallback_total),
                "max_reason_missing_total": int(args.max_reason_missing_total),
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
    print(f"fallback_coverage_ratio={_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")
    print(f"source_based_response_ratio={_safe_float(summary.get('source_based_response_ratio'), 0.0):.4f}")
    print(f"clarification_ratio={_safe_float(summary.get('clarification_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
