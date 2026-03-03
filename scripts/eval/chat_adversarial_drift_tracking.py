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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "published_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _read_rows(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    rows: list[dict[str, Any]] = []
    try:
        payload = json.loads(text)
    except Exception:
        payload = None

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, Mapping):
                rows.append({str(k): v for k, v in item.items()})
    else:
        for line in text.splitlines():
            row_text = line.strip()
            if not row_text:
                continue
            try:
                item = json.loads(row_text)
            except Exception:
                continue
            if isinstance(item, Mapping):
                rows.append({str(k): v for k, v in item.items()})

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def _version_id(row: Mapping[str, Any]) -> str:
    for key in ("dataset_version", "version", "suite_version", "evalset_version"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return "unknown"


def _case_id(row: Mapping[str, Any]) -> str:
    for key in ("case_id", "id", "dataset_case_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _incident_id(row: Mapping[str, Any]) -> str:
    for key in ("incident_id", "id", "ticket_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _linked_case_id(row: Mapping[str, Any]) -> str:
    for key in ("linked_case_id", "dataset_case_id", "eval_case_id", "case_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _month_key(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _iter_month_keys(start: datetime, end: datetime) -> list[str]:
    start_month = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    end_month = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
    keys: list[str] = []
    cursor = start_month
    while cursor <= end_month:
        keys.append(_month_key(cursor))
        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=timezone.utc)
    return keys


def summarize_drift_tracking(
    dataset_rows: list[Mapping[str, Any]],
    incident_rows: list[Mapping[str, Any]],
    *,
    window_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    window_start = now_dt - timedelta(days=max(1, int(window_days)))

    dataset_case_total = 0
    dataset_versions: set[str] = set()
    dataset_months: set[str] = set()
    latest_dataset_ts: datetime | None = None

    for row in dataset_rows:
        ts = _event_ts(row)
        if ts is not None and ts < window_start:
            continue
        case_id = _case_id(row)
        if not case_id:
            continue
        dataset_case_total += 1
        dataset_versions.add(_version_id(row))
        if ts is not None:
            dataset_months.add(_month_key(ts))
            if latest_dataset_ts is None or ts > latest_dataset_ts:
                latest_dataset_ts = ts

    incident_total = 0
    linked_incident_total = 0
    latest_incident_ts: datetime | None = None
    for row in incident_rows:
        ts = _event_ts(row)
        if ts is not None and ts < window_start:
            continue
        incident_id = _incident_id(row)
        if not incident_id and not _linked_case_id(row):
            continue
        incident_total += 1
        if _linked_case_id(row):
            linked_incident_total += 1
        if ts is not None and (latest_incident_ts is None or ts > latest_incident_ts):
            latest_incident_ts = ts

    expected_months = _iter_month_keys(window_start, now_dt)
    missing_monthly_refresh_total = len(set(expected_months) - dataset_months)
    dataset_version_total = len(dataset_versions)
    refresh_age_days = 999999.0 if latest_dataset_ts is None else max(0.0, (now_dt - latest_dataset_ts).total_seconds() / 86400.0)
    incident_unlinked_total = max(0, incident_total - linked_incident_total)
    incident_link_ratio = 1.0 if incident_total == 0 else float(linked_incident_total) / float(incident_total)

    latest_evidence_ts = latest_dataset_ts
    if latest_incident_ts is not None and (latest_evidence_ts is None or latest_incident_ts > latest_evidence_ts):
        latest_evidence_ts = latest_incident_ts
    stale_minutes = 999999.0 if latest_evidence_ts is None else max(0.0, (now_dt - latest_evidence_ts).total_seconds() / 60.0)

    return {
        "dataset_case_total": dataset_case_total,
        "dataset_version_total": dataset_version_total,
        "dataset_month_total": len(dataset_months),
        "missing_monthly_refresh_total": missing_monthly_refresh_total,
        "refresh_age_days": refresh_age_days,
        "incident_total": incident_total,
        "incident_linked_total": linked_incident_total,
        "incident_unlinked_total": incident_unlinked_total,
        "incident_link_ratio": incident_link_ratio,
        "latest_dataset_time": latest_dataset_ts.isoformat() if latest_dataset_ts else None,
        "latest_incident_time": latest_incident_ts.isoformat() if latest_incident_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_dataset_case_total: int,
    min_dataset_version_total: int,
    max_refresh_age_days: float,
    max_missing_monthly_refresh_total: int,
    min_incident_total: int,
    min_incident_link_ratio: float,
    max_unlinked_incident_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    dataset_case_total = _safe_int(summary.get("dataset_case_total"), 0)
    dataset_version_total = _safe_int(summary.get("dataset_version_total"), 0)
    refresh_age_days = _safe_float(summary.get("refresh_age_days"), 999999.0)
    missing_monthly_refresh_total = _safe_int(summary.get("missing_monthly_refresh_total"), 0)
    incident_total = _safe_int(summary.get("incident_total"), 0)
    incident_link_ratio = _safe_float(summary.get("incident_link_ratio"), 1.0)
    incident_unlinked_total = _safe_int(summary.get("incident_unlinked_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if dataset_case_total < max(0, int(min_dataset_case_total)):
        failures.append(f"drift dataset case total too small: {dataset_case_total} < {int(min_dataset_case_total)}")
    if dataset_version_total < max(0, int(min_dataset_version_total)):
        failures.append(f"drift dataset version total too small: {dataset_version_total} < {int(min_dataset_version_total)}")
    if refresh_age_days > max(0.0, float(max_refresh_age_days)):
        failures.append(f"drift dataset refresh age too old: {refresh_age_days:.2f}d > {float(max_refresh_age_days):.2f}d")
    if missing_monthly_refresh_total > max(0, int(max_missing_monthly_refresh_total)):
        failures.append(
            "drift monthly refresh gap exceeded: "
            f"{missing_monthly_refresh_total} > {int(max_missing_monthly_refresh_total)}"
        )
    if incident_total < max(0, int(min_incident_total)):
        failures.append(f"drift incident total too small: {incident_total} < {int(min_incident_total)}")
    if incident_link_ratio < max(0.0, float(min_incident_link_ratio)):
        failures.append(
            f"drift incident link ratio below threshold: {incident_link_ratio:.4f} < {float(min_incident_link_ratio):.4f}"
        )
    if incident_unlinked_total > max(0, int(max_unlinked_incident_total)):
        failures.append(
            f"drift unlinked incident total exceeded: {incident_unlinked_total} > {int(max_unlinked_incident_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"drift evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Adversarial Drift Tracking")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- dataset_case_total: {_safe_int(summary.get('dataset_case_total'), 0)}")
    lines.append(f"- dataset_version_total: {_safe_int(summary.get('dataset_version_total'), 0)}")
    lines.append(f"- refresh_age_days: {_safe_float(summary.get('refresh_age_days'), 0.0):.2f}")
    lines.append(f"- incident_total: {_safe_int(summary.get('incident_total'), 0)}")
    lines.append(f"- incident_link_ratio: {_safe_float(summary.get('incident_link_ratio'), 1.0):.4f}")
    lines.append(f"- missing_monthly_refresh_total: {_safe_int(summary.get('missing_monthly_refresh_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Track adversarial evalset drift and incident feedback linkage.")
    parser.add_argument("--dataset-jsonl", default="evaluation/chat_safety/adversarial_cases.jsonl")
    parser.add_argument("--incident-jsonl", default="var/chat_ops/incident_feedback.jsonl")
    parser.add_argument("--window-days", type=int, default=365)
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_adversarial_drift_tracking")
    parser.add_argument("--min-dataset-case-total", type=int, default=0)
    parser.add_argument("--min-dataset-version-total", type=int, default=0)
    parser.add_argument("--max-refresh-age-days", type=float, default=30.0)
    parser.add_argument("--max-missing-monthly-refresh-total", type=int, default=0)
    parser.add_argument("--min-incident-total", type=int, default=0)
    parser.add_argument("--min-incident-link-ratio", type=float, default=0.7)
    parser.add_argument("--max-unlinked-incident-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dataset_rows = _read_rows(Path(args.dataset_jsonl), limit=max(1, int(args.limit)))
    incident_rows = _read_rows(Path(args.incident_jsonl), limit=max(1, int(args.limit)))
    summary = summarize_drift_tracking(
        dataset_rows,
        incident_rows,
        window_days=max(1, int(args.window_days)),
    )
    failures = evaluate_gate(
        summary,
        min_dataset_case_total=max(0, int(args.min_dataset_case_total)),
        min_dataset_version_total=max(0, int(args.min_dataset_version_total)),
        max_refresh_age_days=max(0.0, float(args.max_refresh_age_days)),
        max_missing_monthly_refresh_total=max(0, int(args.max_missing_monthly_refresh_total)),
        min_incident_total=max(0, int(args.min_incident_total)),
        min_incident_link_ratio=max(0.0, float(args.min_incident_link_ratio)),
        max_unlinked_incident_total=max(0, int(args.max_unlinked_incident_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_jsonl": str(args.dataset_jsonl),
        "incident_jsonl": str(args.incident_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_dataset_case_total": int(args.min_dataset_case_total),
                "min_dataset_version_total": int(args.min_dataset_version_total),
                "max_refresh_age_days": float(args.max_refresh_age_days),
                "max_missing_monthly_refresh_total": int(args.max_missing_monthly_refresh_total),
                "min_incident_total": int(args.min_incident_total),
                "min_incident_link_ratio": float(args.min_incident_link_ratio),
                "max_unlinked_incident_total": int(args.max_unlinked_incident_total),
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
    print(f"dataset_case_total={_safe_int(summary.get('dataset_case_total'), 0)}")
    print(f"dataset_version_total={_safe_int(summary.get('dataset_version_total'), 0)}")
    print(f"incident_total={_safe_int(summary.get('incident_total'), 0)}")
    print(f"incident_link_ratio={_safe_float(summary.get('incident_link_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
