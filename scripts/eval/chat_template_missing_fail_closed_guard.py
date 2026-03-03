#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


FAIL_CLOSED_STATUSES = {
    "insufficient_evidence",
    "safe_fallback",
    "degraded",
}

FAIL_CLOSED_ACTIONS = {
    "OPEN_SUPPORT_TICKET",
    "PROVIDE_REQUIRED_INFO",
    "RETRY",
    "REFINE_QUERY",
    "NONE",
}

TEMPLATE_MISSING_REASON_TOKENS = (
    "TEMPLATE_MISSING",
    "TEMPLATE_ROUTE_MISSING",
    "POLICY_TEMPLATE_NOT_FOUND",
)


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


def _template_required(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("template_required"))
    if explicit is not None:
        return explicit
    reason = str(row.get("reason_code") or "").strip()
    return bool(reason)


def _template_key(row: Mapping[str, Any]) -> str:
    return str(row.get("template_key") or row.get("template_id") or row.get("policy_template_key") or "").strip()


def _template_missing(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("template_missing"))
    if explicit is not None:
        return explicit
    if not _template_required(row):
        return False
    return not bool(_template_key(row))


def _fail_closed_enforced(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("fail_closed_enforced"))
    if explicit is not None:
        return explicit
    status = str(row.get("status") or "").strip().lower()
    next_action = str(row.get("next_action") or "").strip().upper()
    blocked = _safe_bool(row.get("response_blocked"))
    if blocked is True:
        return True
    return status in FAIL_CLOSED_STATUSES and next_action in FAIL_CLOSED_ACTIONS


def _unsafe_rendered_when_missing(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("unsafe_rendered_when_missing"))
    if explicit is not None:
        return explicit
    rendered = _safe_bool(row.get("template_rendered"))
    if rendered is not None:
        return rendered
    rendered = _safe_bool(row.get("rendered_template_present"))
    if rendered is not None:
        return rendered
    return False


def _reason_code_text(row: Mapping[str, Any]) -> str:
    reason = row.get("reason_code")
    if isinstance(reason, list):
        return " ".join(str(item) for item in reason)
    return str(reason or row.get("reason_codes") or row.get("violation_codes") or "")


def _template_missing_reason_code_present(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("template_missing_reason_present"))
    if explicit is not None:
        return explicit
    reason_text = _reason_code_text(row).upper()
    return any(token in reason_text for token in TEMPLATE_MISSING_REASON_TOKENS)


def summarize_template_missing_fail_closed_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    template_required_total = 0
    template_missing_total = 0
    fail_closed_enforced_total = 0
    fail_open_violation_total = 0
    unsafe_rendered_when_missing_total = 0
    template_missing_reason_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        required = _template_required(row)
        if required:
            template_required_total += 1

        if not _template_missing(row):
            continue

        template_missing_total += 1
        fail_closed = _fail_closed_enforced(row)
        if fail_closed:
            fail_closed_enforced_total += 1
        else:
            fail_open_violation_total += 1

        if _unsafe_rendered_when_missing(row):
            unsafe_rendered_when_missing_total += 1
        if not _template_missing_reason_code_present(row):
            template_missing_reason_missing_total += 1

    fail_closed_enforcement_ratio = (
        1.0 if template_missing_total == 0 else float(fail_closed_enforced_total) / float(template_missing_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "template_required_total": template_required_total,
        "template_missing_total": template_missing_total,
        "fail_closed_enforced_total": fail_closed_enforced_total,
        "fail_open_violation_total": fail_open_violation_total,
        "unsafe_rendered_when_missing_total": unsafe_rendered_when_missing_total,
        "template_missing_reason_missing_total": template_missing_reason_missing_total,
        "fail_closed_enforcement_ratio": fail_closed_enforcement_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_fail_closed_enforcement_ratio: float,
    max_fail_open_violation_total: int,
    max_unsafe_rendered_when_missing_total: int,
    max_template_missing_reason_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    fail_closed_enforcement_ratio = _safe_float(summary.get("fail_closed_enforcement_ratio"), 0.0)
    fail_open_violation_total = _safe_int(summary.get("fail_open_violation_total"), 0)
    unsafe_rendered_when_missing_total = _safe_int(summary.get("unsafe_rendered_when_missing_total"), 0)
    template_missing_reason_missing_total = _safe_int(summary.get("template_missing_reason_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"template missing window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"template missing event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if fail_closed_enforcement_ratio < max(0.0, float(min_fail_closed_enforcement_ratio)):
        failures.append(
            "template missing fail-closed enforcement ratio below minimum: "
            f"{fail_closed_enforcement_ratio:.4f} < {float(min_fail_closed_enforcement_ratio):.4f}"
        )
    if fail_open_violation_total > max(0, int(max_fail_open_violation_total)):
        failures.append(
            f"template missing fail-open violation total exceeded: {fail_open_violation_total} > {int(max_fail_open_violation_total)}"
        )
    if unsafe_rendered_when_missing_total > max(0, int(max_unsafe_rendered_when_missing_total)):
        failures.append(
            "template missing unsafe-rendered total exceeded: "
            f"{unsafe_rendered_when_missing_total} > {int(max_unsafe_rendered_when_missing_total)}"
        )
    if template_missing_reason_missing_total > max(0, int(max_template_missing_reason_missing_total)):
        failures.append(
            "template missing reason-code-missing total exceeded: "
            f"{template_missing_reason_missing_total} > {int(max_template_missing_reason_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"template missing stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Template Missing Fail-Closed Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- template_missing_total: {_safe_int(summary.get('template_missing_total'), 0)}")
    lines.append(f"- fail_closed_enforcement_ratio: {_safe_float(summary.get('fail_closed_enforcement_ratio'), 0.0):.4f}")
    lines.append(f"- fail_open_violation_total: {_safe_int(summary.get('fail_open_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate template-missing fail-closed quality.")
    parser.add_argument("--events-jsonl", default="var/grounded_answer/template_runtime_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_template_missing_fail_closed_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-fail-closed-enforcement-ratio", type=float, default=0.0)
    parser.add_argument("--max-fail-open-violation-total", type=int, default=1000000)
    parser.add_argument("--max-unsafe-rendered-when-missing-total", type=int, default=1000000)
    parser.add_argument("--max-template-missing-reason-missing-total", type=int, default=1000000)
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
    summary = summarize_template_missing_fail_closed_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_fail_closed_enforcement_ratio=max(0.0, float(args.min_fail_closed_enforcement_ratio)),
        max_fail_open_violation_total=max(0, int(args.max_fail_open_violation_total)),
        max_unsafe_rendered_when_missing_total=max(0, int(args.max_unsafe_rendered_when_missing_total)),
        max_template_missing_reason_missing_total=max(0, int(args.max_template_missing_reason_missing_total)),
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
                "min_fail_closed_enforcement_ratio": float(args.min_fail_closed_enforcement_ratio),
                "max_fail_open_violation_total": int(args.max_fail_open_violation_total),
                "max_unsafe_rendered_when_missing_total": int(args.max_unsafe_rendered_when_missing_total),
                "max_template_missing_reason_missing_total": int(args.max_template_missing_reason_missing_total),
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
    print(f"template_missing_total={_safe_int(summary.get('template_missing_total'), 0)}")
    print(f"fail_closed_enforcement_ratio={_safe_float(summary.get('fail_closed_enforcement_ratio'), 0.0):.4f}")
    print(f"fail_open_violation_total={_safe_int(summary.get('fail_open_violation_total'), 0)}")
    print(
        "unsafe_rendered_when_missing_total="
        f"{_safe_int(summary.get('unsafe_rendered_when_missing_total'), 0)}"
    )
    print(
        "template_missing_reason_missing_total="
        f"{_safe_int(summary.get('template_missing_reason_missing_total'), 0)}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
