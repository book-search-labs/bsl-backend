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


def _runtime_load_event(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("runtime_load_id") or row.get("load_id") or row.get("artifact_id") or "").strip())


def _integrity_checked(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("integrity_checked"), False):
        return True
    return "hash_match" in row or "integrity_mismatch" in row or "runtime_hash" in row


def _integrity_mismatch(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("integrity_mismatch"), False):
        return True
    if "hash_match" in row:
        return not _safe_bool(row.get("hash_match"), True)
    expected = str(row.get("expected_hash") or "").strip()
    runtime_hash = str(row.get("runtime_hash") or row.get("actual_hash") or "").strip()
    if expected and runtime_hash:
        return expected != runtime_hash
    return False


def _fallback_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("fallback_applied"), False):
        return True
    source = str(row.get("load_source") or "").strip().lower()
    if source:
        return source in {"trusted_fallback", "last_stable", "stable_fallback"}
    decision = str(row.get("load_decision") or "").strip().upper()
    return decision in {"FALLBACK", "ROLLBACK"}


def _fallback_success(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("fallback_success"), False):
        return True
    if not _fallback_applied(row):
        return False
    result = str(row.get("load_result") or row.get("result") or "").strip().upper()
    if result:
        return result in {"SUCCESS", "OK", "LOADED"}
    return True


def _trusted_version_loaded(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("trusted_version_loaded"), False):
        return True
    trusted = str(row.get("trusted_version") or row.get("stable_version") or "").strip()
    loaded = str(row.get("loaded_version") or row.get("active_version") or "").strip()
    if trusted and loaded:
        return trusted == loaded
    return _fallback_applied(row)


def _unsafe_load_after_mismatch(row: Mapping[str, Any]) -> bool:
    if not _integrity_mismatch(row):
        return False
    if _fallback_applied(row):
        return False
    decision = str(row.get("load_decision") or "").strip().upper()
    if decision:
        return decision in {"ALLOW", "LOAD", "PROCEED"}
    return _safe_bool(row.get("load_allowed"), True)


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("integrity_reason_code") or "").strip())


def summarize_prompt_runtime_integrity_fallback_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    runtime_load_total = 0
    integrity_checked_total = 0
    integrity_mismatch_total = 0
    fallback_applied_total = 0
    fallback_success_total = 0
    fallback_missing_total = 0
    trusted_version_loaded_total = 0
    unsafe_load_total = 0
    reason_code_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _runtime_load_event(row):
            continue
        runtime_load_total += 1

        checked = _integrity_checked(row)
        mismatch = _integrity_mismatch(row)
        fallback = _fallback_applied(row)
        fallback_success = _fallback_success(row)
        trusted_loaded = _trusted_version_loaded(row)
        unsafe_load = _unsafe_load_after_mismatch(row)
        reason_present = _reason_present(row)

        if checked:
            integrity_checked_total += 1
        if mismatch:
            integrity_mismatch_total += 1
            if not fallback:
                fallback_missing_total += 1
        if fallback:
            fallback_applied_total += 1
            if fallback_success:
                fallback_success_total += 1
        if trusted_loaded:
            trusted_version_loaded_total += 1
        if unsafe_load:
            unsafe_load_total += 1
        if (mismatch or fallback) and not reason_present:
            reason_code_missing_total += 1

    integrity_checked_ratio = 1.0 if runtime_load_total == 0 else float(integrity_checked_total) / float(runtime_load_total)
    fallback_coverage_ratio = (
        1.0 if integrity_mismatch_total == 0 else float(fallback_applied_total) / float(integrity_mismatch_total)
    )
    fallback_success_ratio = 1.0 if fallback_applied_total == 0 else float(fallback_success_total) / float(fallback_applied_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "runtime_load_total": runtime_load_total,
        "integrity_checked_total": integrity_checked_total,
        "integrity_checked_ratio": integrity_checked_ratio,
        "integrity_mismatch_total": integrity_mismatch_total,
        "fallback_applied_total": fallback_applied_total,
        "fallback_success_total": fallback_success_total,
        "fallback_coverage_ratio": fallback_coverage_ratio,
        "fallback_success_ratio": fallback_success_ratio,
        "fallback_missing_total": fallback_missing_total,
        "trusted_version_loaded_total": trusted_version_loaded_total,
        "unsafe_load_total": unsafe_load_total,
        "reason_code_missing_total": reason_code_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_runtime_load_total: int,
    min_integrity_checked_ratio: float,
    min_fallback_coverage_ratio: float,
    min_fallback_success_ratio: float,
    max_fallback_missing_total: int,
    max_unsafe_load_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    runtime_load_total = _safe_int(summary.get("runtime_load_total"), 0)
    integrity_checked_ratio = _safe_float(summary.get("integrity_checked_ratio"), 0.0)
    fallback_coverage_ratio = _safe_float(summary.get("fallback_coverage_ratio"), 0.0)
    fallback_success_ratio = _safe_float(summary.get("fallback_success_ratio"), 0.0)
    fallback_missing_total = _safe_int(summary.get("fallback_missing_total"), 0)
    unsafe_load_total = _safe_int(summary.get("unsafe_load_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat prompt runtime integrity window too small: {window_size} < {int(min_window)}")
    if runtime_load_total < max(0, int(min_runtime_load_total)):
        failures.append(
            f"chat prompt runtime integrity load total too small: {runtime_load_total} < {int(min_runtime_load_total)}"
        )
    if window_size == 0:
        return failures

    if integrity_checked_ratio < max(0.0, float(min_integrity_checked_ratio)):
        failures.append(
            f"chat prompt runtime integrity checked ratio below minimum: {integrity_checked_ratio:.4f} < {float(min_integrity_checked_ratio):.4f}"
        )
    if fallback_coverage_ratio < max(0.0, float(min_fallback_coverage_ratio)):
        failures.append(
            f"chat prompt runtime integrity fallback coverage ratio below minimum: {fallback_coverage_ratio:.4f} < {float(min_fallback_coverage_ratio):.4f}"
        )
    if fallback_success_ratio < max(0.0, float(min_fallback_success_ratio)):
        failures.append(
            f"chat prompt runtime integrity fallback success ratio below minimum: {fallback_success_ratio:.4f} < {float(min_fallback_success_ratio):.4f}"
        )
    if fallback_missing_total > max(0, int(max_fallback_missing_total)):
        failures.append(
            f"chat prompt runtime integrity fallback missing total exceeded: {fallback_missing_total} > {int(max_fallback_missing_total)}"
        )
    if unsafe_load_total > max(0, int(max_unsafe_load_total)):
        failures.append(f"chat prompt runtime integrity unsafe load total exceeded: {unsafe_load_total} > {int(max_unsafe_load_total)}")
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat prompt runtime integrity reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat prompt runtime integrity stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Prompt Runtime Integrity Fallback Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- runtime_load_total: {_safe_int(summary.get('runtime_load_total'), 0)}")
    lines.append(f"- integrity_checked_ratio: {_safe_float(summary.get('integrity_checked_ratio'), 0.0):.4f}")
    lines.append(f"- fallback_coverage_ratio: {_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- unsafe_load_total: {_safe_int(summary.get('unsafe_load_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate runtime prompt integrity mismatch fallback behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_prompt_supply/runtime_integrity_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_prompt_runtime_integrity_fallback_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-runtime-load-total", type=int, default=0)
    parser.add_argument("--min-integrity-checked-ratio", type=float, default=0.0)
    parser.add_argument("--min-fallback-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-fallback-success-ratio", type=float, default=0.0)
    parser.add_argument("--max-fallback-missing-total", type=int, default=1000000)
    parser.add_argument("--max-unsafe-load-total", type=int, default=1000000)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=1000000)
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
    summary = summarize_prompt_runtime_integrity_fallback_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_runtime_load_total=max(0, int(args.min_runtime_load_total)),
        min_integrity_checked_ratio=max(0.0, float(args.min_integrity_checked_ratio)),
        min_fallback_coverage_ratio=max(0.0, float(args.min_fallback_coverage_ratio)),
        min_fallback_success_ratio=max(0.0, float(args.min_fallback_success_ratio)),
        max_fallback_missing_total=max(0, int(args.max_fallback_missing_total)),
        max_unsafe_load_total=max(0, int(args.max_unsafe_load_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
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
                "min_runtime_load_total": int(args.min_runtime_load_total),
                "min_integrity_checked_ratio": float(args.min_integrity_checked_ratio),
                "min_fallback_coverage_ratio": float(args.min_fallback_coverage_ratio),
                "min_fallback_success_ratio": float(args.min_fallback_success_ratio),
                "max_fallback_missing_total": int(args.max_fallback_missing_total),
                "max_unsafe_load_total": int(args.max_unsafe_load_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
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
    print(f"runtime_load_total={_safe_int(summary.get('runtime_load_total'), 0)}")
    print(f"fallback_coverage_ratio={_safe_float(summary.get('fallback_coverage_ratio'), 0.0):.4f}")
    print(f"unsafe_load_total={_safe_int(summary.get('unsafe_load_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
