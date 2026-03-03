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


def _normalization_checked(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("normalization_checked"), False):
        return True
    return "normalization_policy_version" in row


def _term_normalization_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("term_normalization_applied"), False):
        return True
    return _list_count(row.get("term_replacements")) > 0


def _style_normalization_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("style_normalization_applied"), False):
        return True
    return _list_count(row.get("style_rewrites")) > 0


def _edit_ratio(row: Mapping[str, Any]) -> float:
    explicit = row.get("edit_ratio")
    if explicit is not None:
        return max(0.0, min(1.0, _safe_float(explicit, 0.0)))

    before = str(row.get("original_text") or row.get("pre_normalized_text") or "").strip()
    after = str(row.get("normalized_text") or row.get("response_text") or "").strip()
    if not before and not after:
        return 0.0
    if before == after:
        return 0.0

    baseline = max(len(before), 1)
    mismatch = abs(len(before) - len(after))
    mismatch += sum(1 for left, right in zip(before, after) if left != right)
    return max(0.0, min(1.0, float(mismatch) / float(baseline)))


def _excessive_edit(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("excessive_edit_detected"), False):
        return True
    max_ratio = _safe_float(row.get("max_edit_ratio"), 0.35)
    return _edit_ratio(row) > max(0.05, max_ratio)


def _meaning_drift(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("semantic_drift_detected"), False):
        return True
    if "meaning_preserved" in row:
        return not _safe_bool(row.get("meaning_preserved"), True)
    return False


def _fallback_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("fallback_applied"), False):
        return True
    decision = str(row.get("output_decision") or row.get("final_action") or "").strip().upper()
    return decision in {"FALLBACK", "ABSTAIN"}


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("fallback_reason") or "").strip())


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_korean_runtime_normalization_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    response_total = 0
    normalization_checked_total = 0
    normalization_bypass_total = 0
    term_normalization_applied_total = 0
    style_normalization_applied_total = 0
    normalization_applied_total = 0
    excessive_edit_total = 0
    excessive_edit_without_fallback_total = 0
    meaning_drift_total = 0
    fallback_applied_total = 0
    reason_code_missing_total = 0
    edit_ratios: list[float] = []

    for row in rows:
        response_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        checked = _normalization_checked(row)
        if checked:
            normalization_checked_total += 1
        else:
            normalization_bypass_total += 1

        term_applied = _term_normalization_applied(row)
        style_applied = _style_normalization_applied(row)
        if term_applied:
            term_normalization_applied_total += 1
        if style_applied:
            style_normalization_applied_total += 1
        if term_applied or style_applied:
            normalization_applied_total += 1

        edit_ratio = _edit_ratio(row)
        edit_ratios.append(edit_ratio)
        excessive_edit = _excessive_edit(row)
        meaning_drift = _meaning_drift(row)
        fallback_applied = _fallback_applied(row)
        reason_present = _reason_present(row)

        if excessive_edit:
            excessive_edit_total += 1
            if not fallback_applied:
                excessive_edit_without_fallback_total += 1
        if meaning_drift:
            meaning_drift_total += 1
        if fallback_applied:
            fallback_applied_total += 1
        if (excessive_edit or meaning_drift or fallback_applied) and not reason_present:
            reason_code_missing_total += 1

    normalization_checked_ratio = (
        1.0 if response_total == 0 else float(normalization_checked_total) / float(response_total)
    )
    normalization_applied_ratio = (
        1.0 if normalization_checked_total == 0 else float(normalization_applied_total) / float(normalization_checked_total)
    )
    fallback_coverage_ratio = (
        1.0 if excessive_edit_total == 0 else float(fallback_applied_total) / float(excessive_edit_total)
    )
    p95_edit_ratio = _p95(edit_ratios)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "response_total": response_total,
        "normalization_checked_total": normalization_checked_total,
        "normalization_checked_ratio": normalization_checked_ratio,
        "normalization_bypass_total": normalization_bypass_total,
        "term_normalization_applied_total": term_normalization_applied_total,
        "style_normalization_applied_total": style_normalization_applied_total,
        "normalization_applied_total": normalization_applied_total,
        "normalization_applied_ratio": normalization_applied_ratio,
        "excessive_edit_total": excessive_edit_total,
        "excessive_edit_without_fallback_total": excessive_edit_without_fallback_total,
        "meaning_drift_total": meaning_drift_total,
        "fallback_applied_total": fallback_applied_total,
        "fallback_coverage_ratio": fallback_coverage_ratio,
        "reason_code_missing_total": reason_code_missing_total,
        "p95_edit_ratio": p95_edit_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_response_total: int,
    min_normalization_checked_ratio: float,
    min_fallback_coverage_ratio: float,
    max_normalization_bypass_total: int,
    max_meaning_drift_total: int,
    max_excessive_edit_without_fallback_total: int,
    max_reason_code_missing_total: int,
    max_p95_edit_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    response_total = _safe_int(summary.get("response_total"), 0)
    normalization_checked_ratio = _safe_float(summary.get("normalization_checked_ratio"), 0.0)
    fallback_coverage_ratio = _safe_float(summary.get("fallback_coverage_ratio"), 0.0)
    normalization_bypass_total = _safe_int(summary.get("normalization_bypass_total"), 0)
    meaning_drift_total = _safe_int(summary.get("meaning_drift_total"), 0)
    excessive_edit_without_fallback_total = _safe_int(summary.get("excessive_edit_without_fallback_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    p95_edit_ratio = _safe_float(summary.get("p95_edit_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat korean runtime normalization window too small: {window_size} < {int(min_window)}")
    if response_total < max(0, int(min_response_total)):
        failures.append(
            f"chat korean runtime normalization response total too small: {response_total} < {int(min_response_total)}"
        )
    if window_size == 0:
        return failures

    if normalization_checked_ratio < max(0.0, float(min_normalization_checked_ratio)):
        failures.append(
            "chat korean runtime normalization checked ratio below minimum: "
            f"{normalization_checked_ratio:.4f} < {float(min_normalization_checked_ratio):.4f}"
        )
    if fallback_coverage_ratio < max(0.0, float(min_fallback_coverage_ratio)):
        failures.append(
            "chat korean runtime normalization fallback coverage ratio below minimum: "
            f"{fallback_coverage_ratio:.4f} < {float(min_fallback_coverage_ratio):.4f}"
        )
    if normalization_bypass_total > max(0, int(max_normalization_bypass_total)):
        failures.append(
            f"chat korean runtime normalization bypass total exceeded: {normalization_bypass_total} > {int(max_normalization_bypass_total)}"
        )
    if meaning_drift_total > max(0, int(max_meaning_drift_total)):
        failures.append(
            f"chat korean runtime normalization meaning drift total exceeded: {meaning_drift_total} > {int(max_meaning_drift_total)}"
        )
    if excessive_edit_without_fallback_total > max(0, int(max_excessive_edit_without_fallback_total)):
        failures.append(
            "chat korean runtime normalization excessive-edit-without-fallback total exceeded: "
            f"{excessive_edit_without_fallback_total} > {int(max_excessive_edit_without_fallback_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat korean runtime normalization reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if p95_edit_ratio > max(0.0, float(max_p95_edit_ratio)):
        failures.append(
            f"chat korean runtime normalization p95 edit ratio exceeded: {p95_edit_ratio:.4f} > {float(max_p95_edit_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(
            f"chat korean runtime normalization stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Runtime Normalization Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- response_total: {_safe_int(summary.get('response_total'), 0)}")
    lines.append(
        f"- normalization_checked_ratio: {_safe_float(summary.get('normalization_checked_ratio'), 0.0):.4f}"
    )
    lines.append(f"- fallback_coverage_ratio: {_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- meaning_drift_total: {_safe_int(summary.get('meaning_drift_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat korean runtime normalization quality.")
    parser.add_argument("--events-jsonl", default="var/chat_style/runtime_normalization_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_runtime_normalization_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-response-total", type=int, default=0)
    parser.add_argument("--min-normalization-checked-ratio", type=float, default=0.0)
    parser.add_argument("--min-fallback-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-normalization-bypass-total", type=int, default=1000000)
    parser.add_argument("--max-meaning-drift-total", type=int, default=1000000)
    parser.add_argument("--max-excessive-edit-without-fallback-total", type=int, default=1000000)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=1000000)
    parser.add_argument("--max-p95-edit-ratio", type=float, default=1.0)
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
    summary = summarize_korean_runtime_normalization_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_response_total=max(0, int(args.min_response_total)),
        min_normalization_checked_ratio=max(0.0, float(args.min_normalization_checked_ratio)),
        min_fallback_coverage_ratio=max(0.0, float(args.min_fallback_coverage_ratio)),
        max_normalization_bypass_total=max(0, int(args.max_normalization_bypass_total)),
        max_meaning_drift_total=max(0, int(args.max_meaning_drift_total)),
        max_excessive_edit_without_fallback_total=max(0, int(args.max_excessive_edit_without_fallback_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
        max_p95_edit_ratio=max(0.0, float(args.max_p95_edit_ratio)),
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
                "min_normalization_checked_ratio": float(args.min_normalization_checked_ratio),
                "min_fallback_coverage_ratio": float(args.min_fallback_coverage_ratio),
                "max_normalization_bypass_total": int(args.max_normalization_bypass_total),
                "max_meaning_drift_total": int(args.max_meaning_drift_total),
                "max_excessive_edit_without_fallback_total": int(args.max_excessive_edit_without_fallback_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
                "max_p95_edit_ratio": float(args.max_p95_edit_ratio),
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
    print(f"normalization_checked_ratio={_safe_float(summary.get('normalization_checked_ratio'), 0.0):.4f}")
    print(f"fallback_coverage_ratio={_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
