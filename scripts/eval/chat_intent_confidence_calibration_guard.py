#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


INTENT_DOMAIN_MAP: dict[str, str] = {
    "ORDER_STATUS": "ORDER",
    "CANCEL_ORDER": "ORDER",
    "EXCHANGE_REQUEST": "ORDER",
    "DELIVERY_TRACKING": "SHIPPING",
    "SHIPPING_STATUS": "SHIPPING",
    "REFUND_REQUEST": "REFUND",
    "REFUND_STATUS": "REFUND",
    "POLICY_QA": "POLICY",
    "POLICY_CHECK": "POLICY",
}


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


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return None


def _clamp_confidence(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))


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


def _infer_domain(row: Mapping[str, Any], intent: str) -> str:
    explicit = _normalize_token(row.get("domain") or row.get("intent_domain") or row.get("policy_domain"))
    if explicit:
        return explicit
    return INTENT_DOMAIN_MAP.get(intent, "UNKNOWN")


def _raw_confidence(row: Mapping[str, Any]) -> float:
    for key in ("raw_confidence", "predicted_confidence", "confidence", "intent_confidence"):
        if key in row:
            return _clamp_confidence(row.get(key))
    return 0.0


def _calibrated_confidence(row: Mapping[str, Any], raw_confidence: float) -> float:
    for key in ("calibrated_confidence", "confidence_calibrated", "calibrated_probability"):
        if key in row:
            return _clamp_confidence(row.get(key))
    return raw_confidence


def _outcome(row: Mapping[str, Any]) -> int | None:
    parsed = _safe_bool(row.get("is_correct"))
    if parsed is not None:
        return 1 if parsed else 0

    predicted = _normalize_token(row.get("predicted_intent") or row.get("intent"))
    actual = _normalize_token(row.get("actual_intent") or row.get("ground_truth_intent") or row.get("label_intent"))
    if predicted and actual:
        return 1 if predicted == actual else 0
    return None


def _brier(samples: list[tuple[float, int]]) -> float:
    if not samples:
        return 0.0
    total = 0.0
    for confidence, outcome in samples:
        total += (confidence - float(outcome)) ** 2
    return total / float(len(samples))


def _ece(samples: list[tuple[float, int]], bins: int = 10) -> float:
    if not samples:
        return 0.0
    bucket_totals = [0 for _ in range(max(1, int(bins)))]
    bucket_conf_sum = [0.0 for _ in range(max(1, int(bins)))]
    bucket_outcome_sum = [0.0 for _ in range(max(1, int(bins)))]

    bucket_size = len(bucket_totals)
    for confidence, outcome in samples:
        idx = min(bucket_size - 1, int(confidence * bucket_size))
        bucket_totals[idx] += 1
        bucket_conf_sum[idx] += confidence
        bucket_outcome_sum[idx] += float(outcome)

    total = float(len(samples))
    ece = 0.0
    for idx in range(bucket_size):
        count = bucket_totals[idx]
        if count <= 0:
            continue
        avg_conf = bucket_conf_sum[idx] / float(count)
        avg_outcome = bucket_outcome_sum[idx] / float(count)
        ece += (float(count) / total) * abs(avg_outcome - avg_conf)
    return ece


def summarize_intent_confidence_calibration_guard(
    rows: list[Mapping[str, Any]],
    *,
    required_domains: set[str],
    overconfidence_threshold: float,
    underconfidence_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    prediction_total = 0
    overconfidence_total = 0
    underconfidence_total = 0
    domain_counts: dict[str, int] = {}
    intent_counts: dict[str, dict[str, Any]] = {}
    raw_samples: list[tuple[float, int]] = []
    calibrated_samples: list[tuple[float, int]] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        intent = _normalize_token(row.get("intent") or row.get("predicted_intent") or "UNKNOWN")
        domain = _infer_domain(row, intent)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

        outcome = _outcome(row)
        if outcome is None:
            continue

        prediction_total += 1
        raw_conf = _raw_confidence(row)
        calibrated_conf = _calibrated_confidence(row, raw_conf)
        raw_samples.append((raw_conf, outcome))
        calibrated_samples.append((calibrated_conf, outcome))

        intent_stat = intent_counts.setdefault(
            intent,
            {
                "intent": intent,
                "count": 0,
                "correct_total": 0,
                "overconfidence_total": 0,
                "underconfidence_total": 0,
                "avg_calibrated_confidence": 0.0,
            },
        )
        intent_stat["count"] += 1
        intent_stat["correct_total"] += outcome
        intent_stat["avg_calibrated_confidence"] += calibrated_conf

        if calibrated_conf >= overconfidence_threshold and outcome == 0:
            overconfidence_total += 1
            intent_stat["overconfidence_total"] += 1
        if calibrated_conf <= underconfidence_threshold and outcome == 1:
            underconfidence_total += 1
            intent_stat["underconfidence_total"] += 1

    for stat in intent_counts.values():
        count = _safe_int(stat.get("count"), 0)
        correct_total = _safe_int(stat.get("correct_total"), 0)
        avg_cal = _safe_float(stat.get("avg_calibrated_confidence"), 0.0)
        stat["accuracy"] = 0.0 if count == 0 else float(correct_total) / float(count)
        stat["avg_calibrated_confidence"] = 0.0 if count == 0 else avg_cal / float(count)

    calibrated_brier_score = _brier(calibrated_samples)
    raw_brier_score = _brier(raw_samples)
    calibrated_ece = _ece(calibrated_samples)
    raw_ece = _ece(raw_samples)
    ece_gain = raw_ece - calibrated_ece
    brier_gain = raw_brier_score - calibrated_brier_score

    required_domain_total = len(required_domains)
    covered_required_domains = sorted([domain for domain in required_domains if domain in domain_counts])
    domain_coverage_ratio = 1.0 if required_domain_total == 0 else float(len(covered_required_domains)) / float(required_domain_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "prediction_total": prediction_total,
        "raw_brier_score": raw_brier_score,
        "calibrated_brier_score": calibrated_brier_score,
        "raw_ece": raw_ece,
        "calibrated_ece": calibrated_ece,
        "ece_gain": ece_gain,
        "brier_gain": brier_gain,
        "overconfidence_total": overconfidence_total,
        "underconfidence_total": underconfidence_total,
        "required_domain_total": required_domain_total,
        "covered_required_domain_total": len(covered_required_domains),
        "covered_required_domains": covered_required_domains,
        "domain_coverage_ratio": domain_coverage_ratio,
        "domain_distribution": [{"domain": key, "count": value} for key, value in sorted(domain_counts.items(), key=lambda item: item[0])],
        "intent_distribution": sorted(intent_counts.values(), key=lambda item: str(item.get("intent"))),
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_prediction_total: int,
    min_domain_coverage_ratio: float,
    max_calibrated_ece: float,
    max_calibrated_brier_score: float,
    min_ece_gain: float,
    min_brier_gain: float,
    max_overconfidence_total: int,
    max_underconfidence_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    prediction_total = _safe_int(summary.get("prediction_total"), 0)
    domain_coverage_ratio = _safe_float(summary.get("domain_coverage_ratio"), 0.0)
    calibrated_ece = _safe_float(summary.get("calibrated_ece"), 0.0)
    calibrated_brier_score = _safe_float(summary.get("calibrated_brier_score"), 0.0)
    ece_gain = _safe_float(summary.get("ece_gain"), 0.0)
    brier_gain = _safe_float(summary.get("brier_gain"), 0.0)
    overconfidence_total = _safe_int(summary.get("overconfidence_total"), 0)
    underconfidence_total = _safe_int(summary.get("underconfidence_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"intent calibration window too small: {window_size} < {int(min_window)}")
    if prediction_total < max(0, int(min_prediction_total)):
        failures.append(f"intent calibration prediction total too small: {prediction_total} < {int(min_prediction_total)}")
    if window_size == 0:
        return failures

    if domain_coverage_ratio < max(0.0, float(min_domain_coverage_ratio)):
        failures.append(
            f"intent calibration domain coverage ratio below minimum: {domain_coverage_ratio:.4f} < {float(min_domain_coverage_ratio):.4f}"
        )
    if calibrated_ece > max(0.0, float(max_calibrated_ece)):
        failures.append(f"intent calibration ECE exceeded: {calibrated_ece:.6f} > {float(max_calibrated_ece):.6f}")
    if calibrated_brier_score > max(0.0, float(max_calibrated_brier_score)):
        failures.append(
            f"intent calibration Brier score exceeded: {calibrated_brier_score:.6f} > {float(max_calibrated_brier_score):.6f}"
        )
    if ece_gain < float(min_ece_gain):
        failures.append(f"intent calibration ECE gain below minimum: {ece_gain:.6f} < {float(min_ece_gain):.6f}")
    if brier_gain < float(min_brier_gain):
        failures.append(f"intent calibration Brier gain below minimum: {brier_gain:.6f} < {float(min_brier_gain):.6f}")
    if overconfidence_total > max(0, int(max_overconfidence_total)):
        failures.append(
            f"intent calibration overconfidence total exceeded: {overconfidence_total} > {int(max_overconfidence_total)}"
        )
    if underconfidence_total > max(0, int(max_underconfidence_total)):
        failures.append(
            f"intent calibration underconfidence total exceeded: {underconfidence_total} > {int(max_underconfidence_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"intent calibration stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Intent Confidence Calibration Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- prediction_total: {_safe_int(summary.get('prediction_total'), 0)}")
    lines.append(f"- calibrated_ece: {_safe_float(summary.get('calibrated_ece'), 0.0):.6f}")
    lines.append(f"- calibrated_brier_score: {_safe_float(summary.get('calibrated_brier_score'), 0.0):.6f}")
    lines.append(f"- ece_gain: {_safe_float(summary.get('ece_gain'), 0.0):.6f}")
    lines.append(f"- brier_gain: {_safe_float(summary.get('brier_gain'), 0.0):.6f}")
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
    parser = argparse.ArgumentParser(description="Evaluate intent confidence calibration quality and reliability.")
    parser.add_argument("--events-jsonl", default="var/intent_calibration/intent_predictions.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_intent_confidence_calibration_guard")
    parser.add_argument("--required-domains", default="ORDER,SHIPPING,REFUND,POLICY")
    parser.add_argument("--overconfidence-threshold", type=float, default=0.85)
    parser.add_argument("--underconfidence-threshold", type=float, default=0.35)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-prediction-total", type=int, default=0)
    parser.add_argument("--min-domain-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-calibrated-ece", type=float, default=1000000.0)
    parser.add_argument("--max-calibrated-brier-score", type=float, default=1000000.0)
    parser.add_argument("--min-ece-gain", type=float, default=-1000000.0)
    parser.add_argument("--min-brier-gain", type=float, default=-1000000.0)
    parser.add_argument("--max-overconfidence-total", type=int, default=1000000)
    parser.add_argument("--max-underconfidence-total", type=int, default=1000000)
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
    required_domains = {
        _normalize_token(token)
        for token in str(args.required_domains).split(",")
        if str(token).strip()
    }
    summary = summarize_intent_confidence_calibration_guard(
        rows,
        required_domains=required_domains,
        overconfidence_threshold=_clamp_confidence(args.overconfidence_threshold),
        underconfidence_threshold=_clamp_confidence(args.underconfidence_threshold),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_prediction_total=max(0, int(args.min_prediction_total)),
        min_domain_coverage_ratio=max(0.0, float(args.min_domain_coverage_ratio)),
        max_calibrated_ece=max(0.0, float(args.max_calibrated_ece)),
        max_calibrated_brier_score=max(0.0, float(args.max_calibrated_brier_score)),
        min_ece_gain=float(args.min_ece_gain),
        min_brier_gain=float(args.min_brier_gain),
        max_overconfidence_total=max(0, int(args.max_overconfidence_total)),
        max_underconfidence_total=max(0, int(args.max_underconfidence_total)),
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
                "required_domains": sorted(required_domains),
                "overconfidence_threshold": float(args.overconfidence_threshold),
                "underconfidence_threshold": float(args.underconfidence_threshold),
                "min_window": int(args.min_window),
                "min_prediction_total": int(args.min_prediction_total),
                "min_domain_coverage_ratio": float(args.min_domain_coverage_ratio),
                "max_calibrated_ece": float(args.max_calibrated_ece),
                "max_calibrated_brier_score": float(args.max_calibrated_brier_score),
                "min_ece_gain": float(args.min_ece_gain),
                "min_brier_gain": float(args.min_brier_gain),
                "max_overconfidence_total": int(args.max_overconfidence_total),
                "max_underconfidence_total": int(args.max_underconfidence_total),
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
    print(f"prediction_total={_safe_int(summary.get('prediction_total'), 0)}")
    print(f"calibrated_ece={_safe_float(summary.get('calibrated_ece'), 0.0):.6f}")
    print(f"calibrated_brier_score={_safe_float(summary.get('calibrated_brier_score'), 0.0):.6f}")
    print(f"overconfidence_total={_safe_int(summary.get('overconfidence_total'), 0)}")
    print(f"underconfidence_total={_safe_int(summary.get('underconfidence_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
