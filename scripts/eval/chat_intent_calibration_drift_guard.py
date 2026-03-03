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


def _ratio(numerator: Any, denominator: Any) -> float:
    den = _safe_float(denominator, 0.0)
    if den <= 0.0:
        return 0.0
    return _safe_float(numerator, 0.0) / den


def _metric(row: Mapping[str, Any], key: str, fallback_num: str | None = None, fallback_den: str | None = None) -> float:
    if key in row:
        return max(0.0, _safe_float(row.get(key), 0.0))
    if fallback_num is not None and fallback_den is not None:
        return max(0.0, _ratio(row.get(fallback_num), row.get(fallback_den)))
    return 0.0


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def summarize_intent_calibration_drift_guard(
    rows: list[Mapping[str, Any]],
    *,
    required_intents: set[str],
    recent_hours: int,
    min_baseline_samples: int,
    min_recent_samples: int,
    drift_ece_delta: float,
    drift_brier_delta: float,
    drift_overconfidence_delta: float,
    drift_underconfidence_delta: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    recent_threshold = now_dt - timedelta(hours=max(1, int(recent_hours)))
    latest_ts: datetime | None = None

    per_intent: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        intent = _normalize_token(row.get("intent") or row.get("predicted_intent"))
        if not intent:
            continue

        ece = _metric(row, "calibrated_ece", "ece_total", "ece_count")
        brier = _metric(row, "calibrated_brier_score", "brier_total", "brier_count")
        over_rate = _metric(row, "overconfidence_rate", "overconfidence_total", "prediction_total")
        under_rate = _metric(row, "underconfidence_rate", "underconfidence_total", "prediction_total")

        bucket = "recent" if (ts is not None and ts >= recent_threshold) else "baseline"
        stat = per_intent.setdefault(
            intent,
            {
                "baseline_ece": [],
                "recent_ece": [],
                "baseline_brier": [],
                "recent_brier": [],
                "baseline_over": [],
                "recent_over": [],
                "baseline_under": [],
                "recent_under": [],
            },
        )
        stat[f"{bucket}_ece"].append(ece)
        stat[f"{bucket}_brier"].append(brier)
        stat[f"{bucket}_over"].append(over_rate)
        stat[f"{bucket}_under"].append(under_rate)

    comparable_intent_total = 0
    drifted_intent_total = 0
    missing_required_intent: list[str] = []
    intent_drifts: list[dict[str, Any]] = []
    worst_ece_delta = 0.0
    worst_brier_delta = 0.0
    worst_overconfidence_delta = 0.0
    worst_underconfidence_delta = 0.0

    required = set(required_intents)
    for required_intent in sorted(required):
        if required_intent not in per_intent:
            missing_required_intent.append(required_intent)

    for intent, stat in sorted(per_intent.items(), key=lambda item: item[0]):
        baseline_count = len(stat["baseline_ece"])
        recent_count = len(stat["recent_ece"])
        if baseline_count < max(1, int(min_baseline_samples)) or recent_count < max(1, int(min_recent_samples)):
            continue

        comparable_intent_total += 1
        baseline_ece = _avg(stat["baseline_ece"])
        recent_ece = _avg(stat["recent_ece"])
        baseline_brier = _avg(stat["baseline_brier"])
        recent_brier = _avg(stat["recent_brier"])
        baseline_over = _avg(stat["baseline_over"])
        recent_over = _avg(stat["recent_over"])
        baseline_under = _avg(stat["baseline_under"])
        recent_under = _avg(stat["recent_under"])

        ece_delta = recent_ece - baseline_ece
        brier_delta = recent_brier - baseline_brier
        over_delta = recent_over - baseline_over
        under_delta = recent_under - baseline_under

        worst_ece_delta = max(worst_ece_delta, ece_delta)
        worst_brier_delta = max(worst_brier_delta, brier_delta)
        worst_overconfidence_delta = max(worst_overconfidence_delta, over_delta)
        worst_underconfidence_delta = max(worst_underconfidence_delta, under_delta)

        drifted = (
            ece_delta > max(0.0, float(drift_ece_delta))
            or brier_delta > max(0.0, float(drift_brier_delta))
            or over_delta > max(0.0, float(drift_overconfidence_delta))
            or under_delta > max(0.0, float(drift_underconfidence_delta))
        )
        if drifted:
            drifted_intent_total += 1

        intent_drifts.append(
            {
                "intent": intent,
                "baseline_count": baseline_count,
                "recent_count": recent_count,
                "baseline_ece": baseline_ece,
                "recent_ece": recent_ece,
                "ece_delta": ece_delta,
                "baseline_brier_score": baseline_brier,
                "recent_brier_score": recent_brier,
                "brier_delta": brier_delta,
                "baseline_overconfidence_rate": baseline_over,
                "recent_overconfidence_rate": recent_over,
                "overconfidence_rate_delta": over_delta,
                "baseline_underconfidence_rate": baseline_under,
                "recent_underconfidence_rate": recent_under,
                "underconfidence_rate_delta": under_delta,
                "drifted": drifted,
            }
        )

    drifted_intent_ratio = 1.0 if comparable_intent_total == 0 else float(drifted_intent_total) / float(comparable_intent_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "intent_total": len(per_intent),
        "comparable_intent_total": comparable_intent_total,
        "drifted_intent_total": drifted_intent_total,
        "drifted_intent_ratio": drifted_intent_ratio,
        "missing_required_intent_total": len(missing_required_intent),
        "missing_required_intent": missing_required_intent,
        "worst_ece_delta": worst_ece_delta,
        "worst_brier_delta": worst_brier_delta,
        "worst_overconfidence_rate_delta": worst_overconfidence_delta,
        "worst_underconfidence_rate_delta": worst_underconfidence_delta,
        "intent_drifts": intent_drifts,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_intent_total: int,
    min_comparable_intent_total: int,
    max_drifted_intent_total: int,
    max_worst_ece_delta: float,
    max_worst_brier_delta: float,
    max_worst_overconfidence_rate_delta: float,
    max_worst_underconfidence_rate_delta: float,
    max_missing_required_intent_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    intent_total = _safe_int(summary.get("intent_total"), 0)
    comparable_intent_total = _safe_int(summary.get("comparable_intent_total"), 0)
    drifted_intent_total = _safe_int(summary.get("drifted_intent_total"), 0)
    worst_ece_delta = _safe_float(summary.get("worst_ece_delta"), 0.0)
    worst_brier_delta = _safe_float(summary.get("worst_brier_delta"), 0.0)
    worst_over_delta = _safe_float(summary.get("worst_overconfidence_rate_delta"), 0.0)
    worst_under_delta = _safe_float(summary.get("worst_underconfidence_rate_delta"), 0.0)
    missing_required_intent_total = _safe_int(summary.get("missing_required_intent_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"intent calibration drift window too small: {window_size} < {int(min_window)}")
    if intent_total < max(0, int(min_intent_total)):
        failures.append(f"intent calibration drift intent total too small: {intent_total} < {int(min_intent_total)}")
    if comparable_intent_total < max(0, int(min_comparable_intent_total)):
        failures.append(
            f"intent calibration drift comparable intent total too small: {comparable_intent_total} < {int(min_comparable_intent_total)}"
        )
    if window_size == 0:
        return failures

    if drifted_intent_total > max(0, int(max_drifted_intent_total)):
        failures.append(
            f"intent calibration drifted intent total exceeded: {drifted_intent_total} > {int(max_drifted_intent_total)}"
        )
    if worst_ece_delta > max(0.0, float(max_worst_ece_delta)):
        failures.append(f"intent calibration worst ECE delta exceeded: {worst_ece_delta:.6f} > {float(max_worst_ece_delta):.6f}")
    if worst_brier_delta > max(0.0, float(max_worst_brier_delta)):
        failures.append(
            f"intent calibration worst Brier delta exceeded: {worst_brier_delta:.6f} > {float(max_worst_brier_delta):.6f}"
        )
    if worst_over_delta > max(0.0, float(max_worst_overconfidence_rate_delta)):
        failures.append(
            "intent calibration worst overconfidence-rate delta exceeded: "
            f"{worst_over_delta:.6f} > {float(max_worst_overconfidence_rate_delta):.6f}"
        )
    if worst_under_delta > max(0.0, float(max_worst_underconfidence_rate_delta)):
        failures.append(
            "intent calibration worst underconfidence-rate delta exceeded: "
            f"{worst_under_delta:.6f} > {float(max_worst_underconfidence_rate_delta):.6f}"
        )
    if missing_required_intent_total > max(0, int(max_missing_required_intent_total)):
        failures.append(
            "intent calibration missing required intent total exceeded: "
            f"{missing_required_intent_total} > {int(max_missing_required_intent_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"intent calibration drift stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Intent Calibration Drift Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- comparable_intent_total: {_safe_int(summary.get('comparable_intent_total'), 0)}")
    lines.append(f"- drifted_intent_total: {_safe_int(summary.get('drifted_intent_total'), 0)}")
    lines.append(f"- worst_ece_delta: {_safe_float(summary.get('worst_ece_delta'), 0.0):.6f}")
    lines.append(f"- worst_brier_delta: {_safe_float(summary.get('worst_brier_delta'), 0.0):.6f}")
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
    parser = argparse.ArgumentParser(description="Evaluate intent calibration drift against baseline windows.")
    parser.add_argument("--events-jsonl", default="var/intent_calibration/calibration_metrics.jsonl")
    parser.add_argument("--window-hours", type=int, default=720)
    parser.add_argument("--recent-hours", type=int, default=72)
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_intent_calibration_drift_guard")
    parser.add_argument("--required-intents", default="ORDER_STATUS,DELIVERY_TRACKING,REFUND_REQUEST,POLICY_QA")
    parser.add_argument("--min-baseline-samples", type=int, default=3)
    parser.add_argument("--min-recent-samples", type=int, default=3)
    parser.add_argument("--drift-ece-delta", type=float, default=0.03)
    parser.add_argument("--drift-brier-delta", type=float, default=0.03)
    parser.add_argument("--drift-overconfidence-rate-delta", type=float, default=0.03)
    parser.add_argument("--drift-underconfidence-rate-delta", type=float, default=0.03)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-intent-total", type=int, default=0)
    parser.add_argument("--min-comparable-intent-total", type=int, default=0)
    parser.add_argument("--max-drifted-intent-total", type=int, default=1000000)
    parser.add_argument("--max-worst-ece-delta", type=float, default=1000000.0)
    parser.add_argument("--max-worst-brier-delta", type=float, default=1000000.0)
    parser.add_argument("--max-worst-overconfidence-rate-delta", type=float, default=1000000.0)
    parser.add_argument("--max-worst-underconfidence-rate-delta", type=float, default=1000000.0)
    parser.add_argument("--max-missing-required-intent-total", type=int, default=1000000)
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
    summary = summarize_intent_calibration_drift_guard(
        rows,
        required_intents=required_intents,
        recent_hours=max(1, int(args.recent_hours)),
        min_baseline_samples=max(1, int(args.min_baseline_samples)),
        min_recent_samples=max(1, int(args.min_recent_samples)),
        drift_ece_delta=max(0.0, float(args.drift_ece_delta)),
        drift_brier_delta=max(0.0, float(args.drift_brier_delta)),
        drift_overconfidence_delta=max(0.0, float(args.drift_overconfidence_rate_delta)),
        drift_underconfidence_delta=max(0.0, float(args.drift_underconfidence_rate_delta)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_intent_total=max(0, int(args.min_intent_total)),
        min_comparable_intent_total=max(0, int(args.min_comparable_intent_total)),
        max_drifted_intent_total=max(0, int(args.max_drifted_intent_total)),
        max_worst_ece_delta=max(0.0, float(args.max_worst_ece_delta)),
        max_worst_brier_delta=max(0.0, float(args.max_worst_brier_delta)),
        max_worst_overconfidence_rate_delta=max(0.0, float(args.max_worst_overconfidence_rate_delta)),
        max_worst_underconfidence_rate_delta=max(0.0, float(args.max_worst_underconfidence_rate_delta)),
        max_missing_required_intent_total=max(0, int(args.max_missing_required_intent_total)),
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
                "recent_hours": int(args.recent_hours),
                "min_baseline_samples": int(args.min_baseline_samples),
                "min_recent_samples": int(args.min_recent_samples),
                "drift_ece_delta": float(args.drift_ece_delta),
                "drift_brier_delta": float(args.drift_brier_delta),
                "drift_overconfidence_rate_delta": float(args.drift_overconfidence_rate_delta),
                "drift_underconfidence_rate_delta": float(args.drift_underconfidence_rate_delta),
                "min_window": int(args.min_window),
                "min_intent_total": int(args.min_intent_total),
                "min_comparable_intent_total": int(args.min_comparable_intent_total),
                "max_drifted_intent_total": int(args.max_drifted_intent_total),
                "max_worst_ece_delta": float(args.max_worst_ece_delta),
                "max_worst_brier_delta": float(args.max_worst_brier_delta),
                "max_worst_overconfidence_rate_delta": float(args.max_worst_overconfidence_rate_delta),
                "max_worst_underconfidence_rate_delta": float(args.max_worst_underconfidence_rate_delta),
                "max_missing_required_intent_total": int(args.max_missing_required_intent_total),
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
    print(f"comparable_intent_total={_safe_int(summary.get('comparable_intent_total'), 0)}")
    print(f"drifted_intent_total={_safe_int(summary.get('drifted_intent_total'), 0)}")
    print(f"worst_ece_delta={_safe_float(summary.get('worst_ece_delta'), 0.0):.6f}")
    print(f"worst_brier_delta={_safe_float(summary.get('worst_brier_delta'), 0.0):.6f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
