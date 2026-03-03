#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


SUCCESS_STATUSES = {"SUCCESS", "SUCCEEDED", "COMPLETED", "OK", "DONE"}
FAIL_STATUSES = {"FAIL", "FAILED", "ERROR", "TIMEOUT", "CANCELLED", "ABORTED"}


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _status(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("status") or row.get("run_status") or row.get("result"))


def _is_success(row: Mapping[str, Any]) -> bool:
    status = _status(row)
    if status:
        return status in SUCCESS_STATUSES
    return _safe_bool(row.get("success"), False)


def _is_failed(row: Mapping[str, Any]) -> bool:
    status = _status(row)
    if status:
        return status in FAIL_STATUSES
    return _safe_bool(row.get("failed"), False)


def _threshold_updated(row: Mapping[str, Any]) -> bool:
    if "threshold_updated" in row:
        return _safe_bool(row.get("threshold_updated"), False)
    if _safe_int(row.get("updated_threshold_total"), 0) > 0:
        return True
    if _safe_int(row.get("threshold_update_count"), 0) > 0:
        return True
    return False


def summarize_intent_recalibration_cycle_guard(
    rows: list[Mapping[str, Any]],
    *,
    required_intents: set[str],
    max_recalibration_age_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    successful_run_total = 0
    failed_run_total = 0
    threshold_update_total = 0
    per_intent_success_ts: dict[str, list[datetime]] = {}
    per_intent_run_total: dict[str, int] = {}

    for row in rows:
        ts = _event_ts(row)
        if ts is None:
            continue
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts

        intent = _normalize_token(row.get("intent") or row.get("predicted_intent"))
        if not intent:
            continue

        run_total += 1
        per_intent_run_total[intent] = per_intent_run_total.get(intent, 0) + 1

        if _is_success(row):
            successful_run_total += 1
            per_intent_success_ts.setdefault(intent, []).append(ts)
        elif _is_failed(row):
            failed_run_total += 1

        if _threshold_updated(row):
            threshold_update_total += 1

    required = set(required_intents)
    covered_required_intents: list[str] = []
    stale_required_intents: list[str] = []
    cadence_violation_total = 0
    cadence_violations: list[dict[str, Any]] = []
    intent_freshness: list[dict[str, Any]] = []

    max_age_days = max(1, int(max_recalibration_age_days))
    for intent in sorted(set(list(per_intent_run_total.keys()) + list(required))):
        success_ts = sorted(per_intent_success_ts.get(intent, []))
        last_success = success_ts[-1] if success_ts else None
        age_days = 999999.0 if last_success is None else max(0.0, (now_dt - last_success).total_seconds() / 86400.0)
        is_required = intent in required
        is_covered = bool(is_required and age_days <= float(max_age_days))

        if is_covered:
            covered_required_intents.append(intent)
        if is_required and not is_covered:
            stale_required_intents.append(intent)

        for prev, curr in zip(success_ts, success_ts[1:]):
            gap_days = max(0.0, (curr - prev).total_seconds() / 86400.0)
            if gap_days > float(max_age_days):
                cadence_violation_total += 1
                cadence_violations.append(
                    {
                        "intent": intent,
                        "prev_success_time": prev.isoformat(),
                        "next_success_time": curr.isoformat(),
                        "gap_days": gap_days,
                    }
                )

        intent_freshness.append(
            {
                "intent": intent,
                "required": is_required,
                "run_total": per_intent_run_total.get(intent, 0),
                "success_total": len(success_ts),
                "last_success_time": last_success.isoformat() if last_success else None,
                "last_success_age_days": age_days,
                "covered": is_covered,
            }
        )

    required_total = len(required)
    required_intent_coverage_ratio = (
        1.0 if required_total == 0 else float(len(covered_required_intents)) / float(required_total)
    )
    success_ratio = 1.0 if run_total == 0 else float(successful_run_total) / float(run_total)
    stale_intent_total = len(stale_required_intents)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "successful_run_total": successful_run_total,
        "failed_run_total": failed_run_total,
        "success_ratio": success_ratio,
        "threshold_update_total": threshold_update_total,
        "required_intent_total": required_total,
        "covered_required_intent_total": len(covered_required_intents),
        "required_intent_coverage_ratio": required_intent_coverage_ratio,
        "stale_intent_total": stale_intent_total,
        "stale_required_intents": stale_required_intents,
        "cadence_violation_total": cadence_violation_total,
        "cadence_violations": cadence_violations,
        "intent_freshness": intent_freshness,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_run_total: int,
    min_success_ratio: float,
    min_required_intent_coverage_ratio: float,
    max_failed_run_total: int,
    max_stale_intent_total: int,
    max_cadence_violation_total: int,
    min_threshold_update_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    run_total = _safe_int(summary.get("run_total"), 0)
    success_ratio = _safe_float(summary.get("success_ratio"), 0.0)
    required_intent_coverage_ratio = _safe_float(summary.get("required_intent_coverage_ratio"), 0.0)
    failed_run_total = _safe_int(summary.get("failed_run_total"), 0)
    stale_intent_total = _safe_int(summary.get("stale_intent_total"), 0)
    cadence_violation_total = _safe_int(summary.get("cadence_violation_total"), 0)
    threshold_update_total = _safe_int(summary.get("threshold_update_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"intent recalibration window too small: {window_size} < {int(min_window)}")
    if run_total < max(0, int(min_run_total)):
        failures.append(f"intent recalibration run total too small: {run_total} < {int(min_run_total)}")
    if window_size == 0:
        return failures

    if success_ratio < max(0.0, float(min_success_ratio)):
        failures.append(f"intent recalibration success ratio below minimum: {success_ratio:.4f} < {float(min_success_ratio):.4f}")
    if required_intent_coverage_ratio < max(0.0, float(min_required_intent_coverage_ratio)):
        failures.append(
            "intent recalibration required intent coverage ratio below minimum: "
            f"{required_intent_coverage_ratio:.4f} < {float(min_required_intent_coverage_ratio):.4f}"
        )
    if failed_run_total > max(0, int(max_failed_run_total)):
        failures.append(f"intent recalibration failed run total exceeded: {failed_run_total} > {int(max_failed_run_total)}")
    if stale_intent_total > max(0, int(max_stale_intent_total)):
        failures.append(f"intent recalibration stale intent total exceeded: {stale_intent_total} > {int(max_stale_intent_total)}")
    if cadence_violation_total > max(0, int(max_cadence_violation_total)):
        failures.append(
            f"intent recalibration cadence violation total exceeded: {cadence_violation_total} > {int(max_cadence_violation_total)}"
        )
    if threshold_update_total < max(0, int(min_threshold_update_total)):
        failures.append(
            f"intent recalibration threshold update total below minimum: {threshold_update_total} < {int(min_threshold_update_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"intent recalibration stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Intent Recalibration Cycle Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- run_total: {_safe_int(summary.get('run_total'), 0)}")
    lines.append(f"- success_ratio: {_safe_float(summary.get('success_ratio'), 0.0):.4f}")
    lines.append(f"- required_intent_coverage_ratio: {_safe_float(summary.get('required_intent_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- cadence_violation_total: {_safe_int(summary.get('cadence_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate monthly intent recalibration cycle health.")
    parser.add_argument("--events-jsonl", default="var/intent_calibration/recalibration_runs.jsonl")
    parser.add_argument("--window-hours", type=int, default=2160)  # 90 days
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_intent_recalibration_cycle_guard")
    parser.add_argument("--required-intents", default="ORDER_STATUS,DELIVERY_TRACKING,REFUND_REQUEST,POLICY_QA")
    parser.add_argument("--max-recalibration-age-days", type=int, default=35)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-run-total", type=int, default=0)
    parser.add_argument("--min-success-ratio", type=float, default=0.0)
    parser.add_argument("--min-required-intent-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-failed-run-total", type=int, default=1000000)
    parser.add_argument("--max-stale-intent-total", type=int, default=1000000)
    parser.add_argument("--max-cadence-violation-total", type=int, default=1000000)
    parser.add_argument("--min-threshold-update-total", type=int, default=0)
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
    required_intents = {
        _normalize_token(token)
        for token in str(args.required_intents).split(",")
        if str(token).strip()
    }
    summary = summarize_intent_recalibration_cycle_guard(
        rows,
        required_intents=required_intents,
        max_recalibration_age_days=max(1, int(args.max_recalibration_age_days)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_run_total=max(0, int(args.min_run_total)),
        min_success_ratio=max(0.0, float(args.min_success_ratio)),
        min_required_intent_coverage_ratio=max(0.0, float(args.min_required_intent_coverage_ratio)),
        max_failed_run_total=max(0, int(args.max_failed_run_total)),
        max_stale_intent_total=max(0, int(args.max_stale_intent_total)),
        max_cadence_violation_total=max(0, int(args.max_cadence_violation_total)),
        min_threshold_update_total=max(0, int(args.min_threshold_update_total)),
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
                "required_intents": sorted(required_intents),
                "max_recalibration_age_days": int(args.max_recalibration_age_days),
                "min_window": int(args.min_window),
                "min_run_total": int(args.min_run_total),
                "min_success_ratio": float(args.min_success_ratio),
                "min_required_intent_coverage_ratio": float(args.min_required_intent_coverage_ratio),
                "max_failed_run_total": int(args.max_failed_run_total),
                "max_stale_intent_total": int(args.max_stale_intent_total),
                "max_cadence_violation_total": int(args.max_cadence_violation_total),
                "min_threshold_update_total": int(args.min_threshold_update_total),
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
    print(f"run_total={_safe_int(summary.get('run_total'), 0)}")
    print(f"success_ratio={_safe_float(summary.get('success_ratio'), 0.0):.4f}")
    print(f"required_intent_coverage_ratio={_safe_float(summary.get('required_intent_coverage_ratio'), 0.0):.4f}")
    print(f"cadence_violation_total={_safe_int(summary.get('cadence_violation_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
