#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
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
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_stage(value: Any) -> int | None:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return None
    if text in {"canary", "stage1"}:
        return 1
    if text in {"stage10"}:
        return 10
    if text in {"stage50"}:
        return 50
    if text in {"stable", "stage100"}:
        return 100
    try:
        return int(float(text))
    except Exception:
        return None


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ok", "success", "applied", "completed"}:
        return "SUCCESS"
    if text in {"failed", "error", "timeout", "rollback"}:
        return "FAILED"
    return "UNKNOWN"


def read_events(path: Path, *, window_hours: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = (now or datetime.now(timezone.utc)) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def summarize_distribution(events: list[Mapping[str, Any]], *, required_stages: list[int], now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    success_total = 0
    failure_total = 0
    unknown_total = 0
    signature_invalid_total = 0
    drift_total = 0
    stage_regression_total = 0
    latest_ts: datetime | None = None

    by_bundle_stages: dict[str, set[int]] = {}
    by_bundle_last_stage: dict[str, int] = {}
    drift_by_service: dict[str, int] = {}

    for row in events:
        result = _normalize_result(row.get("result") or row.get("status"))
        bundle_id = str(row.get("bundle_id") or row.get("config_bundle_id") or "UNKNOWN").strip()
        service = str(row.get("service") or row.get("target_service") or "UNKNOWN").strip()
        stage = _normalize_stage(row.get("rollout_stage") or row.get("stage"))
        signature_valid = _safe_bool(row.get("signature_valid"), True)
        desired_version = str(row.get("desired_version") or row.get("target_version") or "").strip()
        applied_version = str(row.get("applied_version") or row.get("current_version") or "").strip()
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if result == "SUCCESS":
            success_total += 1
        elif result == "FAILED":
            failure_total += 1
        else:
            unknown_total += 1

        if not signature_valid:
            signature_invalid_total += 1

        if desired_version and applied_version and desired_version != applied_version:
            drift_total += 1
            drift_by_service[service] = drift_by_service.get(service, 0) + 1

        if stage is not None:
            stages = by_bundle_stages.setdefault(bundle_id, set())
            stages.add(stage)
            previous = by_bundle_last_stage.get(bundle_id)
            if previous is not None and stage < previous:
                stage_regression_total += 1
            if previous is None or stage > previous:
                by_bundle_last_stage[bundle_id] = stage

    window_size = len(events)
    success_ratio = 1.0 if window_size == 0 else float(success_total) / float(window_size)
    drift_ratio = 0.0 if window_size == 0 else float(drift_total) / float(window_size)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    missing_stage_bundles: list[dict[str, Any]] = []
    required_set = set(int(item) for item in required_stages if item > 0)
    for bundle_id, stages in sorted(by_bundle_stages.items(), key=lambda item: item[0]):
        missing = sorted(required_set - stages)
        if missing:
            missing_stage_bundles.append({"bundle_id": bundle_id, "missing_stages": missing})

    return {
        "window_size": window_size,
        "success_total": success_total,
        "failure_total": failure_total,
        "unknown_total": unknown_total,
        "success_ratio": success_ratio,
        "signature_invalid_total": signature_invalid_total,
        "drift_total": drift_total,
        "drift_ratio": drift_ratio,
        "stage_regression_total": stage_regression_total,
        "required_stages": sorted(required_set),
        "bundle_stage_progress": [
            {"bundle_id": bundle_id, "stages": sorted(stages)}
            for bundle_id, stages in sorted(by_bundle_stages.items(), key=lambda item: item[0])
        ],
        "missing_stage_bundles": missing_stage_bundles,
        "drift_by_service": [
            {"service": service, "count": count}
            for service, count in sorted(drift_by_service.items(), key=lambda item: item[1], reverse=True)
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_success_ratio: float,
    max_drift_ratio: float,
    max_signature_invalid_total: int,
    max_stage_regression_total: int,
    max_stale_minutes: float,
    require_stages: bool,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    success_ratio = _safe_float(summary.get("success_ratio"), 0.0)
    drift_ratio = _safe_float(summary.get("drift_ratio"), 0.0)
    signature_invalid_total = _safe_int(summary.get("signature_invalid_total"), 0)
    stage_regression_total = _safe_int(summary.get("stage_regression_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)
    missing_stage_bundles = summary.get("missing_stage_bundles") if isinstance(summary.get("missing_stage_bundles"), list) else []

    if window_size < max(0, int(min_window)):
        failures.append(f"config rollout window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if success_ratio < max(0.0, float(min_success_ratio)):
        failures.append(f"rollout success ratio below threshold: {success_ratio:.4f} < {float(min_success_ratio):.4f}")
    if drift_ratio > max(0.0, float(max_drift_ratio)):
        failures.append(f"config drift ratio exceeded: {drift_ratio:.4f} > {float(max_drift_ratio):.4f}")
    if signature_invalid_total > max(0, int(max_signature_invalid_total)):
        failures.append(
            f"signature invalid events exceeded: {signature_invalid_total} > {int(max_signature_invalid_total)}"
        )
    if stage_regression_total > max(0, int(max_stage_regression_total)):
        failures.append(f"stage regression events exceeded: {stage_regression_total} > {int(max_stage_regression_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"config rollout events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    if require_stages and missing_stage_bundles:
        failures.append(f"required rollout stages missing for {len(missing_stage_bundles)} bundle(s)")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Config Distribution Rollout")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- success_ratio: {_safe_float(summary.get('success_ratio'), 0.0):.4f}")
    lines.append(f"- drift_ratio: {_safe_float(summary.get('drift_ratio'), 0.0):.4f}")
    lines.append(f"- signature_invalid_total: {_safe_int(summary.get('signature_invalid_total'), 0)}")
    lines.append(f"- stage_regression_total: {_safe_int(summary.get('stage_regression_total'), 0)}")
    lines.append(f"- stale_minutes: {_safe_float(summary.get('stale_minutes'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate realtime chat config rollout distribution and drift.")
    parser.add_argument("--events-jsonl", default="var/chat_control/config_rollout_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--required-stages", default="1,10,50,100")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_config_distribution_rollout")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-success-ratio", type=float, default=0.95)
    parser.add_argument("--max-drift-ratio", type=float, default=0.02)
    parser.add_argument("--max-signature-invalid-total", type=int, default=0)
    parser.add_argument("--max-stage-regression-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--require-stages", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    required_stages = [
        _safe_int(token.strip(), -1)
        for token in str(args.required_stages).split(",")
        if token.strip()
    ]

    summary = summarize_distribution(events, required_stages=required_stages)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_success_ratio=max(0.0, float(args.min_success_ratio)),
        max_drift_ratio=max(0.0, float(args.max_drift_ratio)),
        max_signature_invalid_total=max(0, int(args.max_signature_invalid_total)),
        max_stage_regression_total=max(0, int(args.max_stage_regression_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
        require_stages=bool(args.require_stages),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_success_ratio": float(args.min_success_ratio),
                "max_drift_ratio": float(args.max_drift_ratio),
                "max_signature_invalid_total": int(args.max_signature_invalid_total),
                "max_stage_regression_total": int(args.max_stage_regression_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "require_stages": bool(args.require_stages),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"success_ratio={_safe_float(summary.get('success_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
