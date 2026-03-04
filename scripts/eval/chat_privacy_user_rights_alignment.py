#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

DONE_STATUSES = {"DONE", "COMPLETED", "SUCCEEDED", "SUCCESS"}
REQUEST_TYPES = {"DELETE", "EXPORT"}


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items()}


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


def _normalize_request_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "DELETE_REQUEST": "DELETE",
        "ERASURE": "DELETE",
        "EXPORT_REQUEST": "EXPORT",
        "DATA_EXPORT": "EXPORT",
    }
    if text in REQUEST_TYPES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"OK": "DONE", "SUCCESS": "DONE", "FINISHED": "DONE"}
    if text in DONE_STATUSES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _is_completed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("completed"), False):
        return True
    status = _normalize_status(row.get("status") or row.get("result"))
    return status in DONE_STATUSES


def _is_authorized(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("authorized"), True):
        return True
    if _safe_bool(row.get("authz_pass"), False):
        return True
    decision = str(row.get("auth_decision") or "").strip().upper()
    return decision in {"ALLOW", "APPROVED"}


def _delete_cascade_verified(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("cascade_verified"), False):
        return True
    if _safe_bool(row.get("cascade_complete"), False):
        return True
    linked_total = _safe_int(row.get("linked_artifact_total"), 0)
    deleted_total = _safe_int(row.get("linked_artifact_deleted_total"), 0)
    if linked_total > 0 and deleted_total >= linked_total:
        return True
    return False


def _export_consistency_mismatch(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("export_consistency_mismatch"), False):
        return True
    if _safe_bool(row.get("deleted_data_included"), False):
        return True
    check = str(row.get("consistency_check") or "").strip().upper()
    return check == "FAIL"


def summarize_user_rights_alignment(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    request_total = 0
    delete_request_total = 0
    export_request_total = 0
    delete_completed_total = 0
    export_completed_total = 0
    delete_cascade_verified_total = 0
    delete_cascade_miss_total = 0
    export_consistency_mismatch_total = 0
    unauthorized_request_total = 0
    missing_audit_total = 0
    unknown_request_type_total = 0
    request_type_distribution: dict[str, int] = {}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        request_type = _normalize_request_type(row.get("request_type") or row.get("action") or row.get("event_type"))
        request_type_distribution[request_type] = request_type_distribution.get(request_type, 0) + 1
        request_total += 1

        if request_type == "DELETE":
            delete_request_total += 1
        elif request_type == "EXPORT":
            export_request_total += 1
        else:
            unknown_request_type_total += 1
            continue

        authorized = _is_authorized(row)
        if not authorized:
            unauthorized_request_total += 1

        completed = _is_completed(row)
        if request_type == "DELETE":
            if completed:
                delete_completed_total += 1
                if _delete_cascade_verified(row):
                    delete_cascade_verified_total += 1
                else:
                    delete_cascade_miss_total += 1
            if _export_consistency_mismatch(row):
                export_consistency_mismatch_total += 1
        elif request_type == "EXPORT":
            if completed:
                export_completed_total += 1
            if _export_consistency_mismatch(row):
                export_consistency_mismatch_total += 1

        if completed:
            audit_id = str(row.get("audit_id") or row.get("request_audit_id") or "").strip()
            reason_code = str(row.get("reason_code") or row.get("policy_reason") or "").strip()
            if not audit_id or not reason_code:
                missing_audit_total += 1

    delete_completion_ratio = (
        1.0 if delete_request_total == 0 else float(delete_completed_total) / float(max(1, delete_request_total))
    )
    export_completion_ratio = (
        1.0 if export_request_total == 0 else float(export_completed_total) / float(max(1, export_request_total))
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "request_total": request_total,
        "delete_request_total": delete_request_total,
        "export_request_total": export_request_total,
        "delete_completed_total": delete_completed_total,
        "export_completed_total": export_completed_total,
        "delete_completion_ratio": delete_completion_ratio,
        "export_completion_ratio": export_completion_ratio,
        "delete_cascade_verified_total": delete_cascade_verified_total,
        "delete_cascade_miss_total": delete_cascade_miss_total,
        "export_consistency_mismatch_total": export_consistency_mismatch_total,
        "unauthorized_request_total": unauthorized_request_total,
        "missing_audit_total": missing_audit_total,
        "unknown_request_type_total": unknown_request_type_total,
        "request_type_distribution": [
            {"request_type": key, "count": value} for key, value in sorted(request_type_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_delete_request_total: int,
    min_export_request_total: int,
    min_delete_completion_ratio: float,
    min_export_completion_ratio: float,
    max_delete_cascade_miss_total: int,
    max_export_consistency_mismatch_total: int,
    max_unauthorized_request_total: int,
    max_missing_audit_total: int,
    max_unknown_request_type_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    delete_request_total = _safe_int(summary.get("delete_request_total"), 0)
    export_request_total = _safe_int(summary.get("export_request_total"), 0)
    delete_completion_ratio = _safe_float(summary.get("delete_completion_ratio"), 0.0)
    export_completion_ratio = _safe_float(summary.get("export_completion_ratio"), 0.0)
    delete_cascade_miss_total = _safe_int(summary.get("delete_cascade_miss_total"), 0)
    export_consistency_mismatch_total = _safe_int(summary.get("export_consistency_mismatch_total"), 0)
    unauthorized_request_total = _safe_int(summary.get("unauthorized_request_total"), 0)
    missing_audit_total = _safe_int(summary.get("missing_audit_total"), 0)
    unknown_request_type_total = _safe_int(summary.get("unknown_request_type_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat privacy rights window too small: {window_size} < {int(min_window)}")
    if delete_request_total < max(0, int(min_delete_request_total)):
        failures.append(
            f"chat privacy rights delete request total too small: {delete_request_total} < {int(min_delete_request_total)}"
        )
    if export_request_total < max(0, int(min_export_request_total)):
        failures.append(
            f"chat privacy rights export request total too small: {export_request_total} < {int(min_export_request_total)}"
        )
    if window_size == 0:
        return failures

    if delete_completion_ratio < max(0.0, float(min_delete_completion_ratio)):
        failures.append(
            "chat privacy rights delete completion ratio below minimum: "
            f"{delete_completion_ratio:.4f} < {float(min_delete_completion_ratio):.4f}"
        )
    if export_completion_ratio < max(0.0, float(min_export_completion_ratio)):
        failures.append(
            "chat privacy rights export completion ratio below minimum: "
            f"{export_completion_ratio:.4f} < {float(min_export_completion_ratio):.4f}"
        )
    if delete_cascade_miss_total > max(0, int(max_delete_cascade_miss_total)):
        failures.append(
            f"chat privacy rights delete cascade miss total exceeded: {delete_cascade_miss_total} > {int(max_delete_cascade_miss_total)}"
        )
    if export_consistency_mismatch_total > max(0, int(max_export_consistency_mismatch_total)):
        failures.append(
            "chat privacy rights export consistency mismatch total exceeded: "
            f"{export_consistency_mismatch_total} > {int(max_export_consistency_mismatch_total)}"
        )
    if unauthorized_request_total > max(0, int(max_unauthorized_request_total)):
        failures.append(
            f"chat privacy rights unauthorized request total exceeded: {unauthorized_request_total} > {int(max_unauthorized_request_total)}"
        )
    if missing_audit_total > max(0, int(max_missing_audit_total)):
        failures.append(f"chat privacy rights missing audit total exceeded: {missing_audit_total} > {int(max_missing_audit_total)}")
    if unknown_request_type_total > max(0, int(max_unknown_request_type_total)):
        failures.append(
            f"chat privacy rights unknown request type total exceeded: {unknown_request_type_total} > {int(max_unknown_request_type_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat privacy rights stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_delete_request_total_drop: int,
    max_export_request_total_drop: int,
    max_delete_completed_total_drop: int,
    max_export_completed_total_drop: int,
    max_delete_completion_ratio_drop: float,
    max_export_completion_ratio_drop: float,
    max_delete_cascade_miss_total_increase: int,
    max_export_consistency_mismatch_total_increase: int,
    max_unauthorized_request_total_increase: int,
    max_missing_audit_total_increase: int,
    max_unknown_request_type_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("delete_request_total", max_delete_request_total_drop),
        ("export_request_total", max_export_request_total_drop),
        ("delete_completed_total", max_delete_completed_total_drop),
        ("export_completed_total", max_export_completed_total_drop),
    ]
    for key, allowed_drop in baseline_drop_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    base_delete_completion_ratio = _safe_float(base_summary.get("delete_completion_ratio"), 1.0)
    cur_delete_completion_ratio = _safe_float(current_summary.get("delete_completion_ratio"), 1.0)
    delete_completion_ratio_drop = max(0.0, base_delete_completion_ratio - cur_delete_completion_ratio)
    if delete_completion_ratio_drop > max(0.0, float(max_delete_completion_ratio_drop)):
        failures.append(
            "delete_completion_ratio regression: "
            f"baseline={base_delete_completion_ratio:.6f}, current={cur_delete_completion_ratio:.6f}, "
            f"allowed_drop={float(max_delete_completion_ratio_drop):.6f}"
        )

    base_export_completion_ratio = _safe_float(base_summary.get("export_completion_ratio"), 1.0)
    cur_export_completion_ratio = _safe_float(current_summary.get("export_completion_ratio"), 1.0)
    export_completion_ratio_drop = max(0.0, base_export_completion_ratio - cur_export_completion_ratio)
    if export_completion_ratio_drop > max(0.0, float(max_export_completion_ratio_drop)):
        failures.append(
            "export_completion_ratio regression: "
            f"baseline={base_export_completion_ratio:.6f}, current={cur_export_completion_ratio:.6f}, "
            f"allowed_drop={float(max_export_completion_ratio_drop):.6f}"
        )

    baseline_increase_pairs = [
        ("delete_cascade_miss_total", max_delete_cascade_miss_total_increase),
        ("export_consistency_mismatch_total", max_export_consistency_mismatch_total_increase),
        ("unauthorized_request_total", max_unauthorized_request_total_increase),
        ("missing_audit_total", max_missing_audit_total_increase),
        ("unknown_request_type_total", max_unknown_request_type_total_increase),
    ]
    for key, allowed_increase in baseline_increase_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Privacy User Rights Alignment")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- delete_request_total: {_safe_int(summary.get('delete_request_total'), 0)}")
    lines.append(f"- export_request_total: {_safe_int(summary.get('export_request_total'), 0)}")
    lines.append(f"- delete_cascade_miss_total: {_safe_int(summary.get('delete_cascade_miss_total'), 0)}")
    lines.append(f"- export_consistency_mismatch_total: {_safe_int(summary.get('export_consistency_mismatch_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat privacy user rights alignment for export/delete flows.")
    parser.add_argument("--events-jsonl", default="var/chat_privacy/user_rights_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_privacy_user_rights_alignment")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-delete-request-total", type=int, default=0)
    parser.add_argument("--min-export-request-total", type=int, default=0)
    parser.add_argument("--min-delete-completion-ratio", type=float, default=0.0)
    parser.add_argument("--min-export-completion-ratio", type=float, default=0.0)
    parser.add_argument("--max-delete-cascade-miss-total", type=int, default=0)
    parser.add_argument("--max-export-consistency-mismatch-total", type=int, default=0)
    parser.add_argument("--max-unauthorized-request-total", type=int, default=0)
    parser.add_argument("--max-missing-audit-total", type=int, default=0)
    parser.add_argument("--max-unknown-request-type-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-delete-request-total-drop", type=int, default=10)
    parser.add_argument("--max-export-request-total-drop", type=int, default=10)
    parser.add_argument("--max-delete-completed-total-drop", type=int, default=10)
    parser.add_argument("--max-export-completed-total-drop", type=int, default=10)
    parser.add_argument("--max-delete-completion-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-export-completion-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-delete-cascade-miss-total-increase", type=int, default=0)
    parser.add_argument("--max-export-consistency-mismatch-total-increase", type=int, default=0)
    parser.add_argument("--max-unauthorized-request-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-audit-total-increase", type=int, default=0)
    parser.add_argument("--max-unknown-request-type-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_user_rights_alignment(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_delete_request_total=max(0, int(args.min_delete_request_total)),
        min_export_request_total=max(0, int(args.min_export_request_total)),
        min_delete_completion_ratio=max(0.0, float(args.min_delete_completion_ratio)),
        min_export_completion_ratio=max(0.0, float(args.min_export_completion_ratio)),
        max_delete_cascade_miss_total=max(0, int(args.max_delete_cascade_miss_total)),
        max_export_consistency_mismatch_total=max(0, int(args.max_export_consistency_mismatch_total)),
        max_unauthorized_request_total=max(0, int(args.max_unauthorized_request_total)),
        max_missing_audit_total=max(0, int(args.max_missing_audit_total)),
        max_unknown_request_type_total=max(0, int(args.max_unknown_request_type_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_delete_request_total_drop=max(0, int(args.max_delete_request_total_drop)),
            max_export_request_total_drop=max(0, int(args.max_export_request_total_drop)),
            max_delete_completed_total_drop=max(0, int(args.max_delete_completed_total_drop)),
            max_export_completed_total_drop=max(0, int(args.max_export_completed_total_drop)),
            max_delete_completion_ratio_drop=max(0.0, float(args.max_delete_completion_ratio_drop)),
            max_export_completion_ratio_drop=max(0.0, float(args.max_export_completion_ratio_drop)),
            max_delete_cascade_miss_total_increase=max(0, int(args.max_delete_cascade_miss_total_increase)),
            max_export_consistency_mismatch_total_increase=max(0, int(args.max_export_consistency_mismatch_total_increase)),
            max_unauthorized_request_total_increase=max(0, int(args.max_unauthorized_request_total_increase)),
            max_missing_audit_total_increase=max(0, int(args.max_missing_audit_total_increase)),
            max_unknown_request_type_total_increase=max(0, int(args.max_unknown_request_type_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "source": {
            "events_jsonl": str(args.events_jsonl),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_delete_request_total": int(args.min_delete_request_total),
                "min_export_request_total": int(args.min_export_request_total),
                "min_delete_completion_ratio": float(args.min_delete_completion_ratio),
                "min_export_completion_ratio": float(args.min_export_completion_ratio),
                "max_delete_cascade_miss_total": int(args.max_delete_cascade_miss_total),
                "max_export_consistency_mismatch_total": int(args.max_export_consistency_mismatch_total),
                "max_unauthorized_request_total": int(args.max_unauthorized_request_total),
                "max_missing_audit_total": int(args.max_missing_audit_total),
                "max_unknown_request_type_total": int(args.max_unknown_request_type_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_delete_request_total_drop": int(args.max_delete_request_total_drop),
                "max_export_request_total_drop": int(args.max_export_request_total_drop),
                "max_delete_completed_total_drop": int(args.max_delete_completed_total_drop),
                "max_export_completed_total_drop": int(args.max_export_completed_total_drop),
                "max_delete_completion_ratio_drop": float(args.max_delete_completion_ratio_drop),
                "max_export_completion_ratio_drop": float(args.max_export_completion_ratio_drop),
                "max_delete_cascade_miss_total_increase": int(args.max_delete_cascade_miss_total_increase),
                "max_export_consistency_mismatch_total_increase": int(args.max_export_consistency_mismatch_total_increase),
                "max_unauthorized_request_total_increase": int(args.max_unauthorized_request_total_increase),
                "max_missing_audit_total_increase": int(args.max_missing_audit_total_increase),
                "max_unknown_request_type_total_increase": int(args.max_unknown_request_type_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"delete_request_total={_safe_int(summary.get('delete_request_total'), 0)}")
    print(f"delete_cascade_miss_total={_safe_int(summary.get('delete_cascade_miss_total'), 0)}")
    print(f"export_consistency_mismatch_total={_safe_int(summary.get('export_consistency_mismatch_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
