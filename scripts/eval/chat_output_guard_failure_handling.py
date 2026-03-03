#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ALLOWED_FALLBACK_TEMPLATES = {
    "INSUFFICIENT_EVIDENCE_KR",
    "POLICY_BLOCK_KR",
    "TOOL_FAILURE_KR",
    "CLARIFY_REQUIRED_KR",
    "GENERIC_SAFE_FALLBACK_KR",
}
HANGUL_RE = re.compile(r"[가-힣]")
GUARD_FAILURE_RESULTS = {"FAIL", "BLOCK", "DOWNGRADE", "DENY"}


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


def _guard_failed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("guard_failed"), False):
        return True
    result = str(row.get("guard_result") or row.get("contract_result") or "").strip().upper()
    return result in GUARD_FAILURE_RESULTS


def _fallback_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("fallback_applied"), False):
        return True
    decision = str(row.get("output_decision") or row.get("final_action") or "").strip().upper()
    if decision in {"FALLBACK", "ABSTAIN"}:
        return True
    return bool(str(row.get("fallback_template") or "").strip())


def _triage_enqueued(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("triage_enqueued"), False) or _safe_bool(row.get("incident_enqueued"), False):
        return True
    return bool(str(row.get("triage_id") or row.get("ticket_id") or "").strip())


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("guard_reason_code") or "").strip())


def _fallback_template_valid(row: Mapping[str, Any]) -> bool:
    template = str(row.get("fallback_template") or "").strip().upper()
    if not template:
        return False
    return template in ALLOWED_FALLBACK_TEMPLATES


def _fallback_has_korean(row: Mapping[str, Any]) -> bool:
    text = str(row.get("fallback_text") or row.get("response_text") or "").strip()
    if not text:
        return False
    return HANGUL_RE.search(text) is not None


def _failure_time(row: Mapping[str, Any]) -> datetime | None:
    return _parse_ts(row.get("failed_at") or row.get("guard_failed_at")) or _event_ts(row)


def _fallback_latency_ms(row: Mapping[str, Any]) -> float:
    explicit = row.get("failure_to_fallback_latency_ms")
    if explicit is not None:
        return max(0.0, _safe_float(explicit, 0.0))
    failed_at = _failure_time(row)
    fallback_at = _parse_ts(row.get("fallback_at") or row.get("fallback_applied_at"))
    if failed_at is not None and fallback_at is not None:
        return max(0.0, (fallback_at - failed_at).total_seconds() * 1000.0)
    return 0.0


def _triage_latency_ms(row: Mapping[str, Any]) -> float:
    explicit = row.get("failure_to_triage_latency_ms")
    if explicit is not None:
        return max(0.0, _safe_float(explicit, 0.0))
    failed_at = _failure_time(row)
    triage_at = _parse_ts(row.get("triage_at") or row.get("incident_created_at"))
    if failed_at is not None and triage_at is not None:
        return max(0.0, (triage_at - failed_at).total_seconds() * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_output_guard_failure_handling(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    guard_failure_total = 0
    fallback_applied_total = 0
    fallback_template_invalid_total = 0
    fallback_non_korean_total = 0
    triage_enqueued_total = 0
    triage_missing_total = 0
    reason_code_missing_total = 0
    fallback_latency_samples: list[float] = []
    triage_latency_samples: list[float] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _guard_failed(row):
            continue
        guard_failure_total += 1

        fallback = _fallback_applied(row)
        triage = _triage_enqueued(row)
        reason_present = _reason_present(row)

        if fallback:
            fallback_applied_total += 1
            fallback_latency_samples.append(_fallback_latency_ms(row))
            if not _fallback_template_valid(row):
                fallback_template_invalid_total += 1
            if not _fallback_has_korean(row):
                fallback_non_korean_total += 1
        if triage:
            triage_enqueued_total += 1
            triage_latency_samples.append(_triage_latency_ms(row))
        else:
            triage_missing_total += 1

        if not reason_present:
            reason_code_missing_total += 1

    fallback_coverage_ratio = 1.0 if guard_failure_total == 0 else float(fallback_applied_total) / float(guard_failure_total)
    triage_coverage_ratio = 1.0 if guard_failure_total == 0 else float(triage_enqueued_total) / float(guard_failure_total)
    p95_failure_to_fallback_ms = _p95(fallback_latency_samples)
    p95_failure_to_triage_ms = _p95(triage_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "guard_failure_total": guard_failure_total,
        "fallback_applied_total": fallback_applied_total,
        "fallback_coverage_ratio": fallback_coverage_ratio,
        "fallback_template_invalid_total": fallback_template_invalid_total,
        "fallback_non_korean_total": fallback_non_korean_total,
        "triage_enqueued_total": triage_enqueued_total,
        "triage_coverage_ratio": triage_coverage_ratio,
        "triage_missing_total": triage_missing_total,
        "reason_code_missing_total": reason_code_missing_total,
        "p95_failure_to_fallback_ms": p95_failure_to_fallback_ms,
        "p95_failure_to_triage_ms": p95_failure_to_triage_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_guard_failure_total: int,
    min_fallback_coverage_ratio: float,
    min_triage_coverage_ratio: float,
    max_fallback_template_invalid_total: int,
    max_fallback_non_korean_total: int,
    max_reason_code_missing_total: int,
    max_triage_missing_total: int,
    max_p95_failure_to_fallback_ms: float,
    max_p95_failure_to_triage_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    guard_failure_total = _safe_int(summary.get("guard_failure_total"), 0)
    fallback_coverage_ratio = _safe_float(summary.get("fallback_coverage_ratio"), 1.0)
    triage_coverage_ratio = _safe_float(summary.get("triage_coverage_ratio"), 1.0)
    fallback_template_invalid_total = _safe_int(summary.get("fallback_template_invalid_total"), 0)
    fallback_non_korean_total = _safe_int(summary.get("fallback_non_korean_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    triage_missing_total = _safe_int(summary.get("triage_missing_total"), 0)
    p95_failure_to_fallback_ms = _safe_float(summary.get("p95_failure_to_fallback_ms"), 0.0)
    p95_failure_to_triage_ms = _safe_float(summary.get("p95_failure_to_triage_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat output failure handling window too small: {window_size} < {int(min_window)}")
    if guard_failure_total < max(0, int(min_guard_failure_total)):
        failures.append(
            f"chat output guard failure total too small: {guard_failure_total} < {int(min_guard_failure_total)}"
        )
    if window_size == 0:
        return failures

    if fallback_coverage_ratio < max(0.0, float(min_fallback_coverage_ratio)):
        failures.append(
            f"chat output fallback coverage ratio below minimum: {fallback_coverage_ratio:.4f} < {float(min_fallback_coverage_ratio):.4f}"
        )
    if triage_coverage_ratio < max(0.0, float(min_triage_coverage_ratio)):
        failures.append(
            f"chat output triage coverage ratio below minimum: {triage_coverage_ratio:.4f} < {float(min_triage_coverage_ratio):.4f}"
        )
    if fallback_template_invalid_total > max(0, int(max_fallback_template_invalid_total)):
        failures.append(
            "chat output fallback template invalid total exceeded: "
            f"{fallback_template_invalid_total} > {int(max_fallback_template_invalid_total)}"
        )
    if fallback_non_korean_total > max(0, int(max_fallback_non_korean_total)):
        failures.append(
            f"chat output fallback non-korean total exceeded: {fallback_non_korean_total} > {int(max_fallback_non_korean_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat output failure reason-code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if triage_missing_total > max(0, int(max_triage_missing_total)):
        failures.append(
            f"chat output triage missing total exceeded: {triage_missing_total} > {int(max_triage_missing_total)}"
        )
    if p95_failure_to_fallback_ms > max(0.0, float(max_p95_failure_to_fallback_ms)):
        failures.append(
            f"chat output failure->fallback p95 exceeded: {p95_failure_to_fallback_ms:.2f}ms > {float(max_p95_failure_to_fallback_ms):.2f}ms"
        )
    if p95_failure_to_triage_ms > max(0.0, float(max_p95_failure_to_triage_ms)):
        failures.append(
            f"chat output failure->triage p95 exceeded: {p95_failure_to_triage_ms:.2f}ms > {float(max_p95_failure_to_triage_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat output failure handling stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Output Guard Failure Handling")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- guard_failure_total: {_safe_int(summary.get('guard_failure_total'), 0)}")
    lines.append(f"- fallback_coverage_ratio: {_safe_float(summary.get('fallback_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- triage_coverage_ratio: {_safe_float(summary.get('triage_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- fallback_template_invalid_total: {_safe_int(summary.get('fallback_template_invalid_total'), 0)}")
    lines.append(f"- reason_code_missing_total: {_safe_int(summary.get('reason_code_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat output guard failure handling quality.")
    parser.add_argument("--events-jsonl", default="var/chat_output_guard/output_guard_failure_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_output_guard_failure_handling")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-guard-failure-total", type=int, default=0)
    parser.add_argument("--min-fallback-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-triage-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-fallback-template-invalid-total", type=int, default=0)
    parser.add_argument("--max-fallback-non-korean-total", type=int, default=0)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=0)
    parser.add_argument("--max-triage-missing-total", type=int, default=0)
    parser.add_argument("--max-p95-failure-to-fallback-ms", type=float, default=1000000.0)
    parser.add_argument("--max-p95-failure-to-triage-ms", type=float, default=1000000.0)
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
    summary = summarize_output_guard_failure_handling(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_guard_failure_total=max(0, int(args.min_guard_failure_total)),
        min_fallback_coverage_ratio=max(0.0, float(args.min_fallback_coverage_ratio)),
        min_triage_coverage_ratio=max(0.0, float(args.min_triage_coverage_ratio)),
        max_fallback_template_invalid_total=max(0, int(args.max_fallback_template_invalid_total)),
        max_fallback_non_korean_total=max(0, int(args.max_fallback_non_korean_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
        max_triage_missing_total=max(0, int(args.max_triage_missing_total)),
        max_p95_failure_to_fallback_ms=max(0.0, float(args.max_p95_failure_to_fallback_ms)),
        max_p95_failure_to_triage_ms=max(0.0, float(args.max_p95_failure_to_triage_ms)),
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
                "min_guard_failure_total": int(args.min_guard_failure_total),
                "min_fallback_coverage_ratio": float(args.min_fallback_coverage_ratio),
                "min_triage_coverage_ratio": float(args.min_triage_coverage_ratio),
                "max_fallback_template_invalid_total": int(args.max_fallback_template_invalid_total),
                "max_fallback_non_korean_total": int(args.max_fallback_non_korean_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
                "max_triage_missing_total": int(args.max_triage_missing_total),
                "max_p95_failure_to_fallback_ms": float(args.max_p95_failure_to_fallback_ms),
                "max_p95_failure_to_triage_ms": float(args.max_p95_failure_to_triage_ms),
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
    print(f"guard_failure_total={_safe_int(summary.get('guard_failure_total'), 0)}")
    print(f"triage_missing_total={_safe_int(summary.get('triage_missing_total'), 0)}")
    print(f"fallback_template_invalid_total={_safe_int(summary.get('fallback_template_invalid_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
