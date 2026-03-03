#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


MISMATCH_REASON_PREFIXES = ("CLAIM_ACTION_MISMATCH", "ACTION_MISMATCH")
SAFE_FALLBACK_ACTIONS = {"ASK", "RETRY", "OPEN_SUPPORT_TICKET", "STATUS_CHECK", "NONE"}


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


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


def _action_value(value: Any) -> str:
    return str(value or "").strip().upper()


def _proposed_action(row: Mapping[str, Any]) -> str:
    proposed = _action_value(row.get("proposed_action"))
    if proposed:
        return proposed
    selected = row.get("proposed_actions")
    if isinstance(selected, list):
        for item in selected:
            action = _action_value(item)
            if action:
                return action
    return ""


def _action_event(row: Mapping[str, Any]) -> bool:
    if row.get("action_event") is not None:
        return _safe_bool(row.get("action_event"))
    return bool(_proposed_action(row))


def _tool_allowed(row: Mapping[str, Any]) -> bool:
    if row.get("tool_allowed") is not None:
        return _safe_bool(row.get("tool_allowed"))
    status = _action_value(row.get("tool_status"))
    if status:
        return status in {"OK", "ALLOWED", "READY", "SUCCESS"}
    return True


def _policy_allowed(row: Mapping[str, Any]) -> bool:
    if row.get("policy_allowed") is not None:
        return _safe_bool(row.get("policy_allowed"))
    status = _action_value(row.get("policy_status"))
    if status:
        return status in {"OK", "ALLOWED", "PASS", "PERMITTED"}
    return True


def _action_executable(row: Mapping[str, Any]) -> bool:
    if row.get("action_executable") is not None:
        return _safe_bool(row.get("action_executable"))
    proposed = _proposed_action(row)
    if not proposed:
        return False
    return _tool_allowed(row) and _policy_allowed(row)


def _mismatch_detected(row: Mapping[str, Any]) -> bool:
    if row.get("mismatch_detected") is not None:
        return _safe_bool(row.get("mismatch_detected"))
    if row.get("claim_action_mismatch") is not None:
        return _safe_bool(row.get("claim_action_mismatch"))
    proposed = _proposed_action(row)
    executed = _action_value(row.get("executed_action"))
    if proposed and executed:
        return proposed != executed
    return False


def _warning_emitted(row: Mapping[str, Any]) -> bool:
    if row.get("warning_emitted") is not None:
        return _safe_bool(row.get("warning_emitted"))
    reason_code = str(row.get("reason_code") or row.get("warning_reason_code") or "").strip().upper()
    if any(reason_code.startswith(prefix) for prefix in MISMATCH_REASON_PREFIXES):
        return True
    warnings = row.get("warnings")
    if isinstance(warnings, list):
        return any(str(item).strip() for item in warnings)
    return False


def _blocked_action_removed(row: Mapping[str, Any]) -> bool:
    if row.get("blocked_action_removed") is not None:
        return _safe_bool(row.get("blocked_action_removed"))
    final_action = _action_value(row.get("final_action"))
    next_action = _action_value(row.get("next_action"))
    if final_action in SAFE_FALLBACK_ACTIONS or next_action in SAFE_FALLBACK_ACTIONS:
        return True
    return False


def summarize_claim_action_consistency_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    action_event_total = 0
    consistency_pass_total = 0
    mismatch_total = 0
    mismatch_warning_missing_total = 0
    infeasible_action_total = 0
    infeasible_action_removed_total = 0
    infeasible_action_removal_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _action_event(row):
            continue
        action_event_total += 1

        executable = _action_executable(row)
        mismatch = _mismatch_detected(row)
        warning = _warning_emitted(row)

        if executable and not mismatch:
            consistency_pass_total += 1

        if mismatch:
            mismatch_total += 1
            if not warning:
                mismatch_warning_missing_total += 1

        if not executable:
            infeasible_action_total += 1
            removed = _blocked_action_removed(row)
            if removed:
                infeasible_action_removed_total += 1
            else:
                infeasible_action_removal_missing_total += 1

    consistency_pass_ratio = 1.0 if action_event_total == 0 else float(consistency_pass_total) / float(action_event_total)
    mismatch_warning_coverage_ratio = (
        1.0 if mismatch_total == 0 else 1.0 - (float(mismatch_warning_missing_total) / float(mismatch_total))
    )
    infeasible_action_removal_ratio = (
        1.0 if infeasible_action_total == 0 else float(infeasible_action_removed_total) / float(infeasible_action_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "action_event_total": action_event_total,
        "consistency_pass_total": consistency_pass_total,
        "consistency_pass_ratio": consistency_pass_ratio,
        "mismatch_total": mismatch_total,
        "mismatch_warning_missing_total": mismatch_warning_missing_total,
        "mismatch_warning_coverage_ratio": mismatch_warning_coverage_ratio,
        "infeasible_action_total": infeasible_action_total,
        "infeasible_action_removed_total": infeasible_action_removed_total,
        "infeasible_action_removal_missing_total": infeasible_action_removal_missing_total,
        "infeasible_action_removal_ratio": infeasible_action_removal_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_consistency_pass_ratio: float,
    min_mismatch_warning_coverage_ratio: float,
    min_infeasible_action_removal_ratio: float,
    max_mismatch_total: int,
    max_mismatch_warning_missing_total: int,
    max_infeasible_action_removal_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    consistency_pass_ratio = _safe_float(summary.get("consistency_pass_ratio"), 0.0)
    mismatch_warning_coverage_ratio = _safe_float(summary.get("mismatch_warning_coverage_ratio"), 0.0)
    infeasible_action_removal_ratio = _safe_float(summary.get("infeasible_action_removal_ratio"), 0.0)
    mismatch_total = _safe_int(summary.get("mismatch_total"), 0)
    mismatch_warning_missing_total = _safe_int(summary.get("mismatch_warning_missing_total"), 0)
    infeasible_action_removal_missing_total = _safe_int(summary.get("infeasible_action_removal_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"claim-action consistency window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"claim-action consistency event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if consistency_pass_ratio < max(0.0, float(min_consistency_pass_ratio)):
        failures.append(
            f"claim-action consistency pass ratio below minimum: {consistency_pass_ratio:.4f} < {float(min_consistency_pass_ratio):.4f}"
        )
    if mismatch_warning_coverage_ratio < max(0.0, float(min_mismatch_warning_coverage_ratio)):
        failures.append(
            "claim-action mismatch warning coverage ratio below minimum: "
            f"{mismatch_warning_coverage_ratio:.4f} < {float(min_mismatch_warning_coverage_ratio):.4f}"
        )
    if infeasible_action_removal_ratio < max(0.0, float(min_infeasible_action_removal_ratio)):
        failures.append(
            "claim-action infeasible removal ratio below minimum: "
            f"{infeasible_action_removal_ratio:.4f} < {float(min_infeasible_action_removal_ratio):.4f}"
        )
    if mismatch_total > max(0, int(max_mismatch_total)):
        failures.append(f"claim-action mismatch total exceeded: {mismatch_total} > {int(max_mismatch_total)}")
    if mismatch_warning_missing_total > max(0, int(max_mismatch_warning_missing_total)):
        failures.append(
            "claim-action mismatch-warning-missing total exceeded: "
            f"{mismatch_warning_missing_total} > {int(max_mismatch_warning_missing_total)}"
        )
    if infeasible_action_removal_missing_total > max(0, int(max_infeasible_action_removal_missing_total)):
        failures.append(
            "claim-action infeasible-removal-missing total exceeded: "
            f"{infeasible_action_removal_missing_total} > {int(max_infeasible_action_removal_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"claim-action consistency stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Claim-Action Consistency Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- consistency_pass_ratio: {_safe_float(summary.get('consistency_pass_ratio'), 0.0):.4f}")
    lines.append(
        f"- mismatch_warning_coverage_ratio: {_safe_float(summary.get('mismatch_warning_coverage_ratio'), 0.0):.4f}"
    )
    lines.append(
        f"- infeasible_action_removal_ratio: {_safe_float(summary.get('infeasible_action_removal_ratio'), 0.0):.4f}"
    )
    lines.append(f"- mismatch_total: {_safe_int(summary.get('mismatch_total'), 0)}")
    lines.append(
        f"- infeasible_action_removal_missing_total: {_safe_int(summary.get('infeasible_action_removal_missing_total'), 0)}"
    )
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
    parser = argparse.ArgumentParser(description="Evaluate claim-to-action consistency quality.")
    parser.add_argument("--events-jsonl", default="var/actionability/claim_action_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_claim_action_consistency_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-consistency-pass-ratio", type=float, default=0.0)
    parser.add_argument("--min-mismatch-warning-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-infeasible-action-removal-ratio", type=float, default=0.0)
    parser.add_argument("--max-mismatch-total", type=int, default=1000000)
    parser.add_argument("--max-mismatch-warning-missing-total", type=int, default=1000000)
    parser.add_argument("--max-infeasible-action-removal-missing-total", type=int, default=1000000)
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
    summary = summarize_claim_action_consistency_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_consistency_pass_ratio=max(0.0, float(args.min_consistency_pass_ratio)),
        min_mismatch_warning_coverage_ratio=max(0.0, float(args.min_mismatch_warning_coverage_ratio)),
        min_infeasible_action_removal_ratio=max(0.0, float(args.min_infeasible_action_removal_ratio)),
        max_mismatch_total=max(0, int(args.max_mismatch_total)),
        max_mismatch_warning_missing_total=max(0, int(args.max_mismatch_warning_missing_total)),
        max_infeasible_action_removal_missing_total=max(0, int(args.max_infeasible_action_removal_missing_total)),
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
                "min_consistency_pass_ratio": float(args.min_consistency_pass_ratio),
                "min_mismatch_warning_coverage_ratio": float(args.min_mismatch_warning_coverage_ratio),
                "min_infeasible_action_removal_ratio": float(args.min_infeasible_action_removal_ratio),
                "max_mismatch_total": int(args.max_mismatch_total),
                "max_mismatch_warning_missing_total": int(args.max_mismatch_warning_missing_total),
                "max_infeasible_action_removal_missing_total": int(args.max_infeasible_action_removal_missing_total),
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
    print(f"consistency_pass_ratio={_safe_float(summary.get('consistency_pass_ratio'), 0.0):.4f}")
    print(f"mismatch_warning_coverage_ratio={_safe_float(summary.get('mismatch_warning_coverage_ratio'), 0.0):.4f}")
    print(f"infeasible_action_removal_ratio={_safe_float(summary.get('infeasible_action_removal_ratio'), 0.0):.4f}")
    print(f"mismatch_total={_safe_int(summary.get('mismatch_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
