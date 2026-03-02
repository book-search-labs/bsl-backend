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
    for key in ("timestamp", "event_time", "ts", "created_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def resolve_latest_report(reports_dir: Path, *, prefix: str) -> Path | None:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not rows:
        return None
    return rows[-1]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


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


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def summarize_calibration(
    events: list[Mapping[str, Any]],
    *,
    forecast_peak_rps: float,
    under_tolerance_ratio: float,
    over_tolerance_ratio: float,
    base_prescale_factor: float,
    calibration_step: float,
) -> dict[str, Any]:
    total = len(events)
    under_total = 0
    over_total = 0
    canary_failure_total = 0
    release_event_total = 0
    scale_up_total = 0
    scale_down_total = 0

    mape_samples: list[float] = []
    peak_actual_rps = 0.0
    peak_allocated_rps = 0.0

    for row in events:
        actual_rps = max(0.0, _safe_float(row.get("actual_rps"), 0.0))
        allocated_rps = max(0.0, _safe_float(row.get("allocated_rps"), 0.0))
        predicted_rps = max(0.0, _safe_float(row.get("predicted_rps"), forecast_peak_rps))
        is_release_event = _safe_bool(row.get("release_event"), False)
        canary_pass = _safe_bool(row.get("canary_pass"), True)
        action = str(row.get("scale_action") or "").strip().lower()

        peak_actual_rps = max(peak_actual_rps, actual_rps)
        peak_allocated_rps = max(peak_allocated_rps, allocated_rps)

        if actual_rps > allocated_rps * (1.0 + max(0.0, under_tolerance_ratio)):
            under_total += 1
        if allocated_rps > actual_rps * (1.0 + max(0.0, over_tolerance_ratio)):
            over_total += 1

        if is_release_event:
            release_event_total += 1
            if not canary_pass:
                canary_failure_total += 1

        if action in {"up", "scale_up", "upscale"}:
            scale_up_total += 1
        if action in {"down", "scale_down", "downscale"}:
            scale_down_total += 1

        denom = max(1.0, actual_rps)
        mape_samples.append(abs(predicted_rps - actual_rps) / denom)

    under_ratio = 0.0 if total == 0 else float(under_total) / float(total)
    over_ratio = 0.0 if total == 0 else float(over_total) / float(total)
    canary_failure_ratio = 0.0 if release_event_total == 0 else float(canary_failure_total) / float(release_event_total)
    prediction_mape = _mean(mape_samples)

    target_prescale_factor = max(1.0, float(base_prescale_factor))
    if under_ratio > over_ratio:
        target_prescale_factor += max(0.0, float(calibration_step))
    elif over_ratio > under_ratio:
        target_prescale_factor = max(1.0, target_prescale_factor - max(0.0, float(calibration_step)))

    recommended_peak_rps = max(float(forecast_peak_rps), peak_actual_rps) * target_prescale_factor

    return {
        "window_size": total,
        "under_total": under_total,
        "over_total": over_total,
        "under_ratio": under_ratio,
        "over_ratio": over_ratio,
        "canary_failure_total": canary_failure_total,
        "release_event_total": release_event_total,
        "canary_failure_ratio": canary_failure_ratio,
        "scale_up_total": scale_up_total,
        "scale_down_total": scale_down_total,
        "prediction_mape": prediction_mape,
        "peak_actual_rps": peak_actual_rps,
        "peak_allocated_rps": peak_allocated_rps,
        "forecast_peak_rps": float(forecast_peak_rps),
        "target_prescale_factor": target_prescale_factor,
        "recommended_peak_rps": recommended_peak_rps,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_under_ratio: float,
    max_over_ratio: float,
    max_prediction_mape: float,
    max_canary_failure_total: int,
    require_release_canary: bool,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    under_ratio = _safe_float(summary.get("under_ratio"), 0.0)
    over_ratio = _safe_float(summary.get("over_ratio"), 0.0)
    prediction_mape = _safe_float(summary.get("prediction_mape"), 0.0)
    canary_failure_total = _safe_int(summary.get("canary_failure_total"), 0)
    release_event_total = _safe_int(summary.get("release_event_total"), 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"autoscaling calibration window too small: {window_size} < {int(min_window)}")
    if under_ratio > max(0.0, float(max_under_ratio)):
        failures.append(f"under-provision ratio exceeded: {under_ratio:.4f} > {float(max_under_ratio):.4f}")
    if over_ratio > max(0.0, float(max_over_ratio)):
        failures.append(f"over-provision ratio exceeded: {over_ratio:.4f} > {float(max_over_ratio):.4f}")
    if prediction_mape > max(0.0, float(max_prediction_mape)):
        failures.append(f"prediction mape exceeded: {prediction_mape:.4f} > {float(max_prediction_mape):.4f}")
    if canary_failure_total > max(0, int(max_canary_failure_total)):
        failures.append(
            f"capacity canary failures exceeded: {canary_failure_total} > {int(max_canary_failure_total)}"
        )
    if require_release_canary and release_event_total <= 0:
        failures.append("release canary evidence required but no release_event samples found")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Autoscaling Calibration")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- capacity_forecast_report: {payload.get('capacity_forecast_report')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- under_ratio: {_safe_float(summary.get('under_ratio'), 0.0):.4f}")
    lines.append(f"- over_ratio: {_safe_float(summary.get('over_ratio'), 0.0):.4f}")
    lines.append(f"- prediction_mape: {_safe_float(summary.get('prediction_mape'), 0.0):.4f}")
    lines.append(f"- canary_failure_total: {_safe_int(summary.get('canary_failure_total'), 0)}")
    lines.append(f"- target_prescale_factor: {_safe_float(summary.get('target_prescale_factor'), 0.0):.4f}")
    lines.append(f"- recommended_peak_rps: {_safe_float(summary.get('recommended_peak_rps'), 0.0):.4f}")

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
    parser = argparse.ArgumentParser(description="Calibrate autoscaling policy using capacity forecast and observed scaling events.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/autoscaling_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=168)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--capacity-forecast-prefix", default="chat_capacity_forecast")
    parser.add_argument("--capacity-forecast-report", default="")
    parser.add_argument("--under-tolerance-ratio", type=float, default=0.05)
    parser.add_argument("--over-tolerance-ratio", type=float, default=0.10)
    parser.add_argument("--base-prescale-factor", type=float, default=1.20)
    parser.add_argument("--calibration-step", type=float, default=0.05)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_autoscaling_calibration")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-under-ratio", type=float, default=0.10)
    parser.add_argument("--max-over-ratio", type=float, default=0.35)
    parser.add_argument("--max-prediction-mape", type=float, default=0.40)
    parser.add_argument("--max-canary-failure-total", type=int, default=0)
    parser.add_argument("--require-release-canary", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    forecast_path: Path | None
    if str(args.capacity_forecast_report).strip():
        forecast_path = Path(args.capacity_forecast_report)
        if not forecast_path.exists():
            raise RuntimeError(f"capacity forecast report not found: {forecast_path}")
    else:
        forecast_path = resolve_latest_report(Path(args.reports_dir), prefix=str(args.capacity_forecast_prefix))

    forecast_payload = load_json(forecast_path) if forecast_path else {}
    forecast_summary = forecast_payload.get("summary") if isinstance(forecast_payload.get("summary"), Mapping) else {}
    forecast_forecast = forecast_summary.get("forecast") if isinstance(forecast_summary.get("forecast"), Mapping) else {}
    forecast_peak_rps = _safe_float(forecast_forecast.get("peak_rps"), 0.0)

    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )

    summary = summarize_calibration(
        events,
        forecast_peak_rps=forecast_peak_rps,
        under_tolerance_ratio=max(0.0, float(args.under_tolerance_ratio)),
        over_tolerance_ratio=max(0.0, float(args.over_tolerance_ratio)),
        base_prescale_factor=max(1.0, float(args.base_prescale_factor)),
        calibration_step=max(0.0, float(args.calibration_step)),
    )

    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_under_ratio=max(0.0, float(args.max_under_ratio)),
        max_over_ratio=max(0.0, float(args.max_over_ratio)),
        max_prediction_mape=max(0.0, float(args.max_prediction_mape)),
        max_canary_failure_total=max(0, int(args.max_canary_failure_total)),
        require_release_canary=bool(args.require_release_canary),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "capacity_forecast_report": str(forecast_path) if forecast_path else None,
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_under_ratio": float(args.max_under_ratio),
                "max_over_ratio": float(args.max_over_ratio),
                "max_prediction_mape": float(args.max_prediction_mape),
                "max_canary_failure_total": int(args.max_canary_failure_total),
                "require_release_canary": bool(args.require_release_canary),
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
    print(f"under_ratio={_safe_float(summary.get('under_ratio'), 0.0):.4f}")
    print(f"over_ratio={_safe_float(summary.get('over_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
