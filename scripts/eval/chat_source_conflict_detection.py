#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_CONFLICT_TYPES = {
    "DATE",
    "AMOUNT",
    "POLICY_CONDITION",
    "ELIGIBILITY",
    "DELIVERY_WINDOW",
    "PRICE",
    "OTHER",
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


def _normalize_severity(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"L": "LOW", "M": "MEDIUM", "H": "HIGH"}
    if text in VALID_SEVERITIES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_conflict_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"POLICY": "POLICY_CONDITION", "CONDITION": "POLICY_CONDITION"}
    if text in VALID_CONFLICT_TYPES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _source_count(row: Mapping[str, Any]) -> int:
    if isinstance(row.get("source_count"), int):
        return int(row.get("source_count"))
    sources = row.get("sources")
    if isinstance(sources, list):
        return len(sources)
    count = 0
    if str(row.get("source_a") or "").strip():
        count += 1
    if str(row.get("source_b") or "").strip():
        count += 1
    return count


def _is_conflict(row: Mapping[str, Any], severity: str) -> bool:
    if _safe_bool(row.get("is_conflict"), False):
        return True
    if severity in VALID_SEVERITIES:
        return True
    return _safe_float(row.get("conflict_score"), 0.0) > 0.0


def summarize_conflict_detection(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    conflict_detected_total = 0
    high_conflict_total = 0
    invalid_severity_total = 0
    missing_topic_total = 0
    missing_conflict_type_total = 0
    missing_source_pair_total = 0
    missing_evidence_total = 0
    severity_distribution: dict[str, int] = {}

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        severity = _normalize_severity(row.get("conflict_severity") or row.get("severity"))
        conflict_type = _normalize_conflict_type(row.get("conflict_type") or row.get("fact_type"))
        if _is_conflict(row, severity):
            conflict_detected_total += 1
            severity_distribution[severity] = severity_distribution.get(severity, 0) + 1
            if severity == "HIGH":
                high_conflict_total += 1
            if severity not in VALID_SEVERITIES:
                invalid_severity_total += 1

            topic_key = str(row.get("topic_key") or row.get("topic") or row.get("policy_topic") or "").strip()
            if not topic_key:
                missing_topic_total += 1
            if conflict_type not in VALID_CONFLICT_TYPES:
                missing_conflict_type_total += 1
            if _source_count(row) < 2:
                missing_source_pair_total += 1

            evidence = row.get("evidence")
            has_evidence = False
            if isinstance(evidence, list) and len(evidence) > 0:
                has_evidence = True
            if isinstance(evidence, Mapping) and len(evidence) > 0:
                has_evidence = True
            if str(row.get("evidence_link") or row.get("evidence_id") or "").strip():
                has_evidence = True
            if not has_evidence:
                missing_evidence_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "conflict_detected_total": conflict_detected_total,
        "high_conflict_total": high_conflict_total,
        "invalid_severity_total": invalid_severity_total,
        "missing_topic_total": missing_topic_total,
        "missing_conflict_type_total": missing_conflict_type_total,
        "missing_source_pair_total": missing_source_pair_total,
        "missing_evidence_total": missing_evidence_total,
        "severity_distribution": [
            {"severity": key, "count": value} for key, value in sorted(severity_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_conflict_detected_total: int,
    max_invalid_severity_total: int,
    max_missing_topic_total: int,
    max_missing_conflict_type_total: int,
    max_missing_source_pair_total: int,
    max_missing_evidence_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    conflict_detected_total = _safe_int(summary.get("conflict_detected_total"), 0)
    invalid_severity_total = _safe_int(summary.get("invalid_severity_total"), 0)
    missing_topic_total = _safe_int(summary.get("missing_topic_total"), 0)
    missing_conflict_type_total = _safe_int(summary.get("missing_conflict_type_total"), 0)
    missing_source_pair_total = _safe_int(summary.get("missing_source_pair_total"), 0)
    missing_evidence_total = _safe_int(summary.get("missing_evidence_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"source conflict detection window too small: {window_size} < {int(min_window)}")
    if conflict_detected_total < max(0, int(min_conflict_detected_total)):
        failures.append(
            f"source conflict detected total too small: {conflict_detected_total} < {int(min_conflict_detected_total)}"
        )
    if window_size == 0:
        return failures

    if invalid_severity_total > max(0, int(max_invalid_severity_total)):
        failures.append(
            f"source conflict invalid severity total exceeded: {invalid_severity_total} > {int(max_invalid_severity_total)}"
        )
    if missing_topic_total > max(0, int(max_missing_topic_total)):
        failures.append(f"source conflict missing topic total exceeded: {missing_topic_total} > {int(max_missing_topic_total)}")
    if missing_conflict_type_total > max(0, int(max_missing_conflict_type_total)):
        failures.append(
            "source conflict missing conflict type total exceeded: "
            f"{missing_conflict_type_total} > {int(max_missing_conflict_type_total)}"
        )
    if missing_source_pair_total > max(0, int(max_missing_source_pair_total)):
        failures.append(
            f"source conflict missing source pair total exceeded: {missing_source_pair_total} > {int(max_missing_source_pair_total)}"
        )
    if missing_evidence_total > max(0, int(max_missing_evidence_total)):
        failures.append(
            f"source conflict missing evidence total exceeded: {missing_evidence_total} > {int(max_missing_evidence_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"source conflict detection stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Source Conflict Detection")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- conflicts_jsonl: {payload.get('conflicts_jsonl')}")
    lines.append(f"- conflict_detected_total: {_safe_int(summary.get('conflict_detected_total'), 0)}")
    lines.append(f"- high_conflict_total: {_safe_int(summary.get('high_conflict_total'), 0)}")
    lines.append(f"- missing_source_pair_total: {_safe_int(summary.get('missing_source_pair_total'), 0)}")
    lines.append(f"- missing_evidence_total: {_safe_int(summary.get('missing_evidence_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate source conflict detection quality.")
    parser.add_argument("--conflicts-jsonl", default="var/chat_trust/source_conflicts.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_source_conflict_detection")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-conflict-detected-total", type=int, default=0)
    parser.add_argument("--max-invalid-severity-total", type=int, default=0)
    parser.add_argument("--max-missing-topic-total", type=int, default=0)
    parser.add_argument("--max-missing-conflict-type-total", type=int, default=0)
    parser.add_argument("--max-missing-source-pair-total", type=int, default=0)
    parser.add_argument("--max-missing-evidence-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.conflicts_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_conflict_detection(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_conflict_detected_total=max(0, int(args.min_conflict_detected_total)),
        max_invalid_severity_total=max(0, int(args.max_invalid_severity_total)),
        max_missing_topic_total=max(0, int(args.max_missing_topic_total)),
        max_missing_conflict_type_total=max(0, int(args.max_missing_conflict_type_total)),
        max_missing_source_pair_total=max(0, int(args.max_missing_source_pair_total)),
        max_missing_evidence_total=max(0, int(args.max_missing_evidence_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conflicts_jsonl": str(args.conflicts_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_conflict_detected_total": int(args.min_conflict_detected_total),
                "max-invalid-severity-total": int(args.max_invalid_severity_total),
                "max-missing-topic-total": int(args.max_missing_topic_total),
                "max-missing-conflict-type-total": int(args.max_missing_conflict_type_total),
                "max-missing-source-pair-total": int(args.max_missing_source_pair_total),
                "max-missing-evidence-total": int(args.max_missing_evidence_total),
                "max-stale-minutes": float(args.max_stale_minutes),
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
    print(f"conflict_detected_total={_safe_int(summary.get('conflict_detected_total'), 0)}")
    print(f"high_conflict_total={_safe_int(summary.get('high_conflict_total'), 0)}")
    print(f"missing_evidence_total={_safe_int(summary.get('missing_evidence_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
