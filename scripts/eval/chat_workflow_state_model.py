#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_WORKFLOW_TYPES = {"CANCEL_ORDER", "REFUND_REQUEST", "ADDRESS_CHANGE"}


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
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at", "last_action_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "ORDER_CANCEL": "CANCEL_ORDER",
        "CANCEL": "CANCEL_ORDER",
        "REFUND": "REFUND_REQUEST",
        "ADDRESS_UPDATE": "ADDRESS_CHANGE",
        "CHANGE_ADDRESS": "ADDRESS_CHANGE",
    }
    if text in SUPPORTED_WORKFLOW_TYPES:
        return text
    return aliases.get(text, text or "UNKNOWN")


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


def summarize_workflow_state(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    state_record_total = 0
    missing_state_fields_total = 0
    unsupported_type_total = 0
    recovery_checkpoint_total = 0
    by_type: dict[str, dict[str, int]] = {}
    workflow_ids: set[str] = set()

    for row in events:
        workflow_id = str(row.get("workflow_id") or row.get("id") or "").strip()
        workflow_type = _normalize_type(row.get("workflow_type") or row.get("type"))
        current_step = str(row.get("current_step") or row.get("step") or "").strip()
        required_inputs = row.get("required_inputs")
        last_action_at = str(row.get("last_action_at") or "").strip()
        checkpoint_id = str(row.get("checkpoint_id") or row.get("recovery_token") or "").strip()
        resumable = _safe_bool(row.get("resumable"), False)
        event_name = str(row.get("event_type") or row.get("status") or "").strip().upper()
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if workflow_id:
            workflow_ids.add(workflow_id)

        state_record_total += 1
        has_required_inputs = isinstance(required_inputs, list) and len(required_inputs) >= 0
        if not workflow_id or not current_step or not has_required_inputs or not last_action_at:
            missing_state_fields_total += 1

        if workflow_type not in SUPPORTED_WORKFLOW_TYPES:
            unsupported_type_total += 1

        if checkpoint_id or resumable:
            recovery_checkpoint_total += 1

        type_row = by_type.setdefault(workflow_type, {"total": 0, "started": 0, "completed": 0})
        type_row["total"] += 1
        if event_name in {"START", "STARTED", "INIT"}:
            type_row["started"] += 1
        if event_name in {"COMPLETED", "EXECUTED", "DONE"}:
            type_row["completed"] += 1

    workflow_total = len(workflow_ids)
    checkpoint_ratio = 0.0 if workflow_total == 0 else float(recovery_checkpoint_total) / float(workflow_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    missing_templates = sorted(
        list(SUPPORTED_WORKFLOW_TYPES - {workflow_type for workflow_type in by_type.keys() if workflow_type in SUPPORTED_WORKFLOW_TYPES})
    )

    return {
        "window_size": len(events),
        "workflow_total": workflow_total,
        "state_record_total": state_record_total,
        "missing_state_fields_total": missing_state_fields_total,
        "unsupported_type_total": unsupported_type_total,
        "recovery_checkpoint_total": recovery_checkpoint_total,
        "checkpoint_ratio": checkpoint_ratio,
        "missing_templates": missing_templates,
        "by_type": [
            {
                "workflow_type": workflow_type,
                "total": values["total"],
                "started": values["started"],
                "completed": values["completed"],
            }
            for workflow_type, values in sorted(by_type.items(), key=lambda item: item[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_state_fields_total: int,
    max_unsupported_type_total: int,
    min_checkpoint_ratio: float,
    max_stale_minutes: float,
    require_templates: bool,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_state_fields_total = _safe_int(summary.get("missing_state_fields_total"), 0)
    unsupported_type_total = _safe_int(summary.get("unsupported_type_total"), 0)
    checkpoint_ratio = _safe_float(summary.get("checkpoint_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)
    missing_templates = summary.get("missing_templates") if isinstance(summary.get("missing_templates"), list) else []

    if window_size < max(0, int(min_window)):
        failures.append(f"workflow state window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_state_fields_total > max(0, int(max_missing_state_fields_total)):
        failures.append(
            f"missing state fields total exceeded: {missing_state_fields_total} > {int(max_missing_state_fields_total)}"
        )
    if unsupported_type_total > max(0, int(max_unsupported_type_total)):
        failures.append(f"unsupported workflow type total exceeded: {unsupported_type_total} > {int(max_unsupported_type_total)}")
    if checkpoint_ratio < max(0.0, float(min_checkpoint_ratio)):
        failures.append(f"checkpoint ratio below threshold: {checkpoint_ratio:.4f} < {float(min_checkpoint_ratio):.4f}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"workflow state events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    if require_templates and missing_templates:
        failures.append(f"required workflow templates missing: {','.join(str(item) for item in missing_templates)}")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Workflow State Model")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- workflow_total: {_safe_int(summary.get('workflow_total'), 0)}")
    lines.append(f"- missing_state_fields_total: {_safe_int(summary.get('missing_state_fields_total'), 0)}")
    lines.append(f"- unsupported_type_total: {_safe_int(summary.get('unsupported_type_total'), 0)}")
    lines.append(f"- checkpoint_ratio: {_safe_float(summary.get('checkpoint_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat workflow state model quality for commerce workflows.")
    parser.add_argument("--events-jsonl", default="var/chat_workflow/workflow_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_workflow_state_model")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-missing-state-fields-total", type=int, default=0)
    parser.add_argument("--max-unsupported-type-total", type=int, default=0)
    parser.add_argument("--min-checkpoint-ratio", type=float, default=0.80)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--require-templates", action="store_true")
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
    summary = summarize_workflow_state(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_state_fields_total=max(0, int(args.max_missing_state_fields_total)),
        max_unsupported_type_total=max(0, int(args.max_unsupported_type_total)),
        min_checkpoint_ratio=max(0.0, float(args.min_checkpoint_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
        require_templates=bool(args.require_templates),
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
                "max_missing_state_fields_total": int(args.max_missing_state_fields_total),
                "max_unsupported_type_total": int(args.max_unsupported_type_total),
                "min_checkpoint_ratio": float(args.min_checkpoint_ratio),
                "max_stale_minutes": float(args.max_stale_minutes),
                "require_templates": bool(args.require_templates),
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
    print(f"workflow_total={_safe_int(summary.get('workflow_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
