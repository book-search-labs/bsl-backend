#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


BAND_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_band(value: Any) -> str:
    token = _normalize_token(value)
    if token in BAND_ORDER:
        return token
    if token in {"0", "RISK_0"}:
        return "R0"
    if token in {"1", "RISK_1"}:
        return "R1"
    if token in {"2", "RISK_2"}:
        return "R2"
    if token in {"3", "RISK_3"}:
        return "R3"
    if token.startswith("R") and len(token) >= 2 and token[1].isdigit():
        band = f"R{token[1]}"
        if band in BAND_ORDER:
            return band
    return ""


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


def _intent_sensitivity_score(row: Mapping[str, Any]) -> float:
    numeric = row.get("intent_sensitivity_score")
    if numeric is None:
        numeric = row.get("intent_sensitivity")
    if isinstance(numeric, (int, float, str)):
        value = _safe_float(numeric, -1.0)
        if value >= 0.0:
            return min(1.0, max(0.0, value))
    level = _normalize_token(row.get("intent_sensitivity_level") or row.get("intent_risk_level"))
    if level in {"HIGH", "H"}:
        return 1.0
    if level in {"MEDIUM", "M"}:
        return 0.6
    if level in {"LOW", "L"}:
        return 0.2
    return 0.0


def _claim_count(row: Mapping[str, Any]) -> int:
    for key in ("claim_count", "claims_total", "assertion_count"):
        if row.get(key) is not None:
            return max(0, _safe_int(row.get(key), 0))
    return 0


def _evidence_trust(row: Mapping[str, Any]) -> float:
    for key in ("evidence_trust_score", "source_trust_score", "citation_trust_score"):
        if row.get(key) is not None:
            value = _safe_float(row.get(key), 1.0)
            return min(1.0, max(0.0, value))
    return 1.0


def _policy_conflict(row: Mapping[str, Any]) -> bool:
    for key in ("policy_conflict", "policy_conflict_detected", "policy_mismatch"):
        explicit = _safe_bool(row.get(key))
        if explicit is not None:
            return explicit
    token = _normalize_token(row.get("policy_conflict_level") or row.get("policy_result"))
    return token in {"CONFLICT", "VIOLATION", "MISMATCH"}


def _infer_expected_band(row: Mapping[str, Any]) -> str:
    score = 0
    if _policy_conflict(row):
        score += 3

    sensitivity = _intent_sensitivity_score(row)
    if sensitivity >= 0.8:
        score += 2
    elif sensitivity >= 0.5:
        score += 1

    claims = _claim_count(row)
    if claims >= 3:
        score += 1
    if claims >= 5:
        score += 1

    trust = _evidence_trust(row)
    if trust < 0.6:
        score += 1
    if trust < 0.3:
        score += 1

    if score >= 6:
        return "R3"
    if score >= 4:
        return "R2"
    if score >= 2:
        return "R1"
    return "R0"


def summarize_answer_risk_band_model_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    missing_band_total = 0
    high_risk_expected_total = 0
    high_risk_covered_total = 0
    underband_total = 0
    overband_total = 0
    assigned_distribution: dict[str, int] = {band: 0 for band in BAND_ORDER}
    expected_distribution: dict[str, int] = {band: 0 for band in BAND_ORDER}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        assigned_band = _normalize_band(row.get("risk_band") or row.get("assigned_band"))
        expected_band = _infer_expected_band(row)
        expected_distribution[expected_band] += 1

        if BAND_ORDER[expected_band] >= BAND_ORDER["R2"]:
            high_risk_expected_total += 1

        if not assigned_band:
            missing_band_total += 1
            continue

        assigned_distribution[assigned_band] += 1
        if BAND_ORDER[expected_band] >= BAND_ORDER["R2"] and BAND_ORDER[assigned_band] >= BAND_ORDER["R2"]:
            high_risk_covered_total += 1
        if BAND_ORDER[assigned_band] < BAND_ORDER[expected_band]:
            underband_total += 1
        if BAND_ORDER[assigned_band] > BAND_ORDER[expected_band]:
            overband_total += 1

    high_risk_coverage_ratio = (
        1.0 if high_risk_expected_total == 0 else float(high_risk_covered_total) / float(high_risk_expected_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "missing_band_total": missing_band_total,
        "high_risk_expected_total": high_risk_expected_total,
        "high_risk_covered_total": high_risk_covered_total,
        "high_risk_coverage_ratio": high_risk_coverage_ratio,
        "underband_total": underband_total,
        "overband_total": overband_total,
        "assigned_distribution": assigned_distribution,
        "expected_distribution": expected_distribution,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_high_risk_coverage_ratio: float,
    max_missing_band_total: int,
    max_underband_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    high_risk_coverage_ratio = _safe_float(summary.get("high_risk_coverage_ratio"), 0.0)
    missing_band_total = _safe_int(summary.get("missing_band_total"), 0)
    underband_total = _safe_int(summary.get("underband_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"answer risk band window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"answer risk band event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if high_risk_coverage_ratio < max(0.0, float(min_high_risk_coverage_ratio)):
        failures.append(
            "answer risk band high-risk coverage ratio below minimum: "
            f"{high_risk_coverage_ratio:.4f} < {float(min_high_risk_coverage_ratio):.4f}"
        )
    if missing_band_total > max(0, int(max_missing_band_total)):
        failures.append(
            f"answer risk band missing-band total exceeded: {missing_band_total} > {int(max_missing_band_total)}"
        )
    if underband_total > max(0, int(max_underband_total)):
        failures.append(f"answer risk band underband total exceeded: {underband_total} > {int(max_underband_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"answer risk band stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Answer Risk Band Model Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- high_risk_coverage_ratio: {_safe_float(summary.get('high_risk_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- missing_band_total: {_safe_int(summary.get('missing_band_total'), 0)}")
    lines.append(f"- underband_total: {_safe_int(summary.get('underband_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate answer risk band model consistency.")
    parser.add_argument("--events-jsonl", default="var/risk_banding/risk_band_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_answer_risk_band_model_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-high-risk-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-band-total", type=int, default=1000000)
    parser.add_argument("--max-underband-total", type=int, default=1000000)
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
    summary = summarize_answer_risk_band_model_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_high_risk_coverage_ratio=max(0.0, float(args.min_high_risk_coverage_ratio)),
        max_missing_band_total=max(0, int(args.max_missing_band_total)),
        max_underband_total=max(0, int(args.max_underband_total)),
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
                "min_event_total": int(args.min_event_total),
                "min_high_risk_coverage_ratio": float(args.min_high_risk_coverage_ratio),
                "max_missing_band_total": int(args.max_missing_band_total),
                "max_underband_total": int(args.max_underband_total),
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
    print(f"high_risk_coverage_ratio={_safe_float(summary.get('high_risk_coverage_ratio'), 0.0):.4f}")
    print(f"missing_band_total={_safe_int(summary.get('missing_band_total'), 0)}")
    print(f"underband_total={_safe_int(summary.get('underband_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
