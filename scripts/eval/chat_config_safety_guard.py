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


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * min(1.0, max(0.0, ratio))))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


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


def summarize_safety_guard(
    events: list[Mapping[str, Any]],
    *,
    forbidden_killswitch_scopes: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    anomaly_total = 0
    handled_anomaly_total = 0
    auto_stop_total = 0
    auto_rollback_total = 0
    killswitch_total = 0
    forbidden_killswitch_total = 0
    detection_lag_samples: list[float] = []
    latest_ts: datetime | None = None
    killswitch_by_scope: dict[str, int] = {}

    for row in events:
        anomaly = _safe_bool(row.get("anomaly_detected"), False) or _safe_bool(row.get("slo_breach"), False) or _safe_bool(
            row.get("quality_breach"), False
        ) or _safe_bool(row.get("cost_breach"), False)
        auto_stop = _safe_bool(row.get("auto_stop"), False)
        auto_rollback = _safe_bool(row.get("auto_rollback"), False)
        killswitch = _safe_bool(row.get("killswitch_activated"), False) or _safe_bool(row.get("kill_switch"), False)
        killswitch_scope = str(row.get("killswitch_scope") or row.get("scope") or "NONE").strip().upper() or "NONE"
        detection_lag_sec = max(0.0, _safe_float(row.get("detection_lag_sec"), 0.0))
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        detection_lag_samples.append(detection_lag_sec)

        if anomaly:
            anomaly_total += 1
            if auto_stop or auto_rollback or killswitch:
                handled_anomaly_total += 1

        if auto_stop:
            auto_stop_total += 1
        if auto_rollback:
            auto_rollback_total += 1
        if killswitch:
            killswitch_total += 1
            killswitch_by_scope[killswitch_scope] = killswitch_by_scope.get(killswitch_scope, 0) + 1
            if killswitch_scope in forbidden_killswitch_scopes:
                forbidden_killswitch_total += 1

    window_size = len(events)
    mitigation_ratio = 1.0 if anomaly_total == 0 else float(handled_anomaly_total) / float(anomaly_total)
    unhandled_anomaly_total = max(0, anomaly_total - handled_anomaly_total)
    detection_lag_p95_sec = _percentile(detection_lag_samples, 0.95)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": window_size,
        "anomaly_total": anomaly_total,
        "handled_anomaly_total": handled_anomaly_total,
        "unhandled_anomaly_total": unhandled_anomaly_total,
        "mitigation_ratio": mitigation_ratio,
        "auto_stop_total": auto_stop_total,
        "auto_rollback_total": auto_rollback_total,
        "killswitch_total": killswitch_total,
        "forbidden_killswitch_total": forbidden_killswitch_total,
        "detection_lag_p95_sec": detection_lag_p95_sec,
        "killswitch_by_scope": [
            {"scope": scope, "count": count}
            for scope, count in sorted(killswitch_by_scope.items(), key=lambda item: item[1], reverse=True)
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_unhandled_anomaly_total: int,
    min_mitigation_ratio: float,
    max_detection_lag_p95_sec: float,
    max_forbidden_killswitch_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    unhandled_anomaly_total = _safe_int(summary.get("unhandled_anomaly_total"), 0)
    mitigation_ratio = _safe_float(summary.get("mitigation_ratio"), 0.0)
    detection_lag_p95_sec = _safe_float(summary.get("detection_lag_p95_sec"), 0.0)
    forbidden_killswitch_total = _safe_int(summary.get("forbidden_killswitch_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"config safety window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if unhandled_anomaly_total > max(0, int(max_unhandled_anomaly_total)):
        failures.append(f"unhandled anomaly total exceeded: {unhandled_anomaly_total} > {int(max_unhandled_anomaly_total)}")
    if mitigation_ratio < max(0.0, float(min_mitigation_ratio)):
        failures.append(f"mitigation ratio below threshold: {mitigation_ratio:.4f} < {float(min_mitigation_ratio):.4f}")
    if detection_lag_p95_sec > max(0.0, float(max_detection_lag_p95_sec)):
        failures.append(
            f"detection lag p95 exceeded: {detection_lag_p95_sec:.1f}s > {float(max_detection_lag_p95_sec):.1f}s"
        )
    if forbidden_killswitch_total > max(0, int(max_forbidden_killswitch_total)):
        failures.append(
            f"forbidden killswitch activation exceeded: {forbidden_killswitch_total} > {int(max_forbidden_killswitch_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"config safety events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Config Safety Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- anomaly_total: {_safe_int(summary.get('anomaly_total'), 0)}")
    lines.append(f"- unhandled_anomaly_total: {_safe_int(summary.get('unhandled_anomaly_total'), 0)}")
    lines.append(f"- mitigation_ratio: {_safe_float(summary.get('mitigation_ratio'), 0.0):.4f}")
    lines.append(f"- auto_stop_total: {_safe_int(summary.get('auto_stop_total'), 0)}")
    lines.append(f"- auto_rollback_total: {_safe_int(summary.get('auto_rollback_total'), 0)}")
    lines.append(f"- killswitch_total: {_safe_int(summary.get('killswitch_total'), 0)}")
    lines.append(f"- detection_lag_p95_sec: {_safe_float(summary.get('detection_lag_p95_sec'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate config rollout safety guard behavior (auto-stop/rollback/killswitch).")
    parser.add_argument("--events-jsonl", default="var/chat_control/config_guard_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--forbidden-killswitch-scopes", default="GLOBAL_ALL_SERVICES")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_config_safety_guard")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-unhandled-anomaly-total", type=int, default=0)
    parser.add_argument("--min-mitigation-ratio", type=float, default=0.95)
    parser.add_argument("--max-detection-lag-p95-sec", type=float, default=120.0)
    parser.add_argument("--max-forbidden-killswitch-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
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
    forbidden_scopes = {
        token.strip().upper()
        for token in str(args.forbidden_killswitch_scopes).split(",")
        if token.strip()
    }
    summary = summarize_safety_guard(events, forbidden_killswitch_scopes=forbidden_scopes)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_unhandled_anomaly_total=max(0, int(args.max_unhandled_anomaly_total)),
        min_mitigation_ratio=max(0.0, float(args.min_mitigation_ratio)),
        max_detection_lag_p95_sec=max(0.0, float(args.max_detection_lag_p95_sec)),
        max_forbidden_killswitch_total=max(0, int(args.max_forbidden_killswitch_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
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
                "max_unhandled_anomaly_total": int(args.max_unhandled_anomaly_total),
                "min_mitigation_ratio": float(args.min_mitigation_ratio),
                "max_detection_lag_p95_sec": float(args.max_detection_lag_p95_sec),
                "max_forbidden_killswitch_total": int(args.max_forbidden_killswitch_total),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"mitigation_ratio={_safe_float(summary.get('mitigation_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
