#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?82[-\s]?)?0?1[0-9][-\s]?\d{3,4}[-\s]?\d{4}\b|\b\d{2,3}[-\s]?\d{3,4}[-\s]?\d{4}\b")
REDACTION_MARKERS = ("***", "[REDACTED]", "<REDACTED>", "(REDACTED)")


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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _pack_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    pack = row.get("evidence_pack")
    if isinstance(pack, Mapping):
        return {str(k): v for k, v in pack.items()}
    return {str(k): v for k, v in row.items()}


def _ticket_id(row: Mapping[str, Any], pack: Mapping[str, Any]) -> str:
    return str(
        pack.get("ticket_id")
        or row.get("ticket_id")
        or pack.get("id")
        or row.get("id")
        or pack.get("case_id")
        or row.get("case_id")
        or ""
    ).strip()


def _extract_tools(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = pack.get("executed_tools")
    if raw is None:
        raw = pack.get("tools")
    if raw is None:
        raw = pack.get("tool_calls")
    if isinstance(raw, list):
        tools: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, Mapping):
                tools.append({str(k): v for k, v in item.items()})
        return tools
    return []


def _has_error_field(pack: Mapping[str, Any]) -> bool:
    for key in ("error_codes", "errors", "error_code", "error"):
        if key in pack:
            return True
    return False


def _has_reference(pack: Mapping[str, Any]) -> bool:
    for key in ("order_id", "shipment_id", "order_ids", "shipment_ids", "reference_ids", "related_ids"):
        value = pack.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
        if str(value or "").strip():
            return True
    return False


def _contains_pii(text: str) -> bool:
    if not text:
        return False
    if EMAIL_RE.search(text):
        return True
    if PHONE_RE.search(text):
        return True
    return False


def _has_redaction(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in REDACTION_MARKERS)


def summarize_evidence_pack_schema(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    seen_tickets: set[str] = set()

    pack_total = 0
    duplicate_ticket_total = 0
    missing_summary_total = 0
    missing_intent_total = 0
    missing_tool_trace_total = 0
    missing_error_code_total = 0
    missing_reference_total = 0
    missing_policy_version_total = 0
    missing_tool_version_total = 0
    redaction_applied_total = 0
    unmasked_pii_total = 0

    for row in rows:
        pack = _pack_payload(row)
        pack_total += 1

        ts = _event_ts(pack) or _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        ticket_id = _ticket_id(row, pack)
        if ticket_id:
            if ticket_id in seen_tickets:
                duplicate_ticket_total += 1
            seen_tickets.add(ticket_id)

        summary = str(pack.get("summary") or pack.get("conversation_summary") or "").strip()
        intent = str(pack.get("intent") or pack.get("user_intent") or "").strip()
        tools = _extract_tools(pack)

        if not summary:
            missing_summary_total += 1
        if not intent:
            missing_intent_total += 1
        if len(tools) == 0:
            missing_tool_trace_total += 1
        if not _has_error_field(pack):
            missing_error_code_total += 1
        if not _has_reference(pack):
            missing_reference_total += 1

        policy_version = str(pack.get("policy_version") or row.get("policy_version") or "").strip()
        if not policy_version:
            missing_policy_version_total += 1

        top_tool_version = str(pack.get("tool_version") or pack.get("tools_version") or "").strip()
        if top_tool_version:
            has_missing_tool_version = False
        elif len(tools) == 0:
            has_missing_tool_version = True
        else:
            has_missing_tool_version = False
            has_version = False
            for tool in tools:
                version = str(tool.get("version") or tool.get("tool_version") or "").strip()
                if version:
                    has_version = True
                else:
                    has_missing_tool_version = True
            if not has_version:
                has_missing_tool_version = True
        if has_missing_tool_version:
            missing_tool_version_total += 1

        text_blob = f"{summary} {str(pack.get('conversation_excerpt') or pack.get('raw_message') or '')}"
        if _contains_pii(text_blob):
            if _has_redaction(text_blob):
                redaction_applied_total += 1
            else:
                unmasked_pii_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "pack_total": pack_total,
        "duplicate_ticket_total": duplicate_ticket_total,
        "missing_summary_total": missing_summary_total,
        "missing_intent_total": missing_intent_total,
        "missing_tool_trace_total": missing_tool_trace_total,
        "missing_error_code_total": missing_error_code_total,
        "missing_reference_total": missing_reference_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_tool_version_total": missing_tool_version_total,
        "redaction_applied_total": redaction_applied_total,
        "unmasked_pii_total": unmasked_pii_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_duplicate_ticket_total: int,
    max_missing_summary_total: int,
    max_missing_intent_total: int,
    max_missing_tool_trace_total: int,
    max_missing_error_code_total: int,
    max_missing_reference_total: int,
    max_missing_policy_version_total: int,
    max_missing_tool_version_total: int,
    max_unmasked_pii_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    duplicate_ticket_total = _safe_int(summary.get("duplicate_ticket_total"), 0)
    missing_summary_total = _safe_int(summary.get("missing_summary_total"), 0)
    missing_intent_total = _safe_int(summary.get("missing_intent_total"), 0)
    missing_tool_trace_total = _safe_int(summary.get("missing_tool_trace_total"), 0)
    missing_error_code_total = _safe_int(summary.get("missing_error_code_total"), 0)
    missing_reference_total = _safe_int(summary.get("missing_reference_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_tool_version_total = _safe_int(summary.get("missing_tool_version_total"), 0)
    unmasked_pii_total = _safe_int(summary.get("unmasked_pii_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket evidence window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if duplicate_ticket_total > max(0, int(max_duplicate_ticket_total)):
        failures.append(f"ticket evidence duplicate ticket total exceeded: {duplicate_ticket_total} > {int(max_duplicate_ticket_total)}")
    if missing_summary_total > max(0, int(max_missing_summary_total)):
        failures.append(f"ticket evidence missing summary total exceeded: {missing_summary_total} > {int(max_missing_summary_total)}")
    if missing_intent_total > max(0, int(max_missing_intent_total)):
        failures.append(f"ticket evidence missing intent total exceeded: {missing_intent_total} > {int(max_missing_intent_total)}")
    if missing_tool_trace_total > max(0, int(max_missing_tool_trace_total)):
        failures.append(
            f"ticket evidence missing tool trace total exceeded: {missing_tool_trace_total} > {int(max_missing_tool_trace_total)}"
        )
    if missing_error_code_total > max(0, int(max_missing_error_code_total)):
        failures.append(
            f"ticket evidence missing error code total exceeded: {missing_error_code_total} > {int(max_missing_error_code_total)}"
        )
    if missing_reference_total > max(0, int(max_missing_reference_total)):
        failures.append(
            f"ticket evidence missing related reference total exceeded: {missing_reference_total} > {int(max_missing_reference_total)}"
        )
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "ticket evidence missing policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_tool_version_total > max(0, int(max_missing_tool_version_total)):
        failures.append(
            f"ticket evidence missing tool version total exceeded: {missing_tool_version_total} > {int(max_missing_tool_version_total)}"
        )
    if unmasked_pii_total > max(0, int(max_unmasked_pii_total)):
        failures.append(f"ticket evidence unmasked PII total exceeded: {unmasked_pii_total} > {int(max_unmasked_pii_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_pack_total_drop: int,
    max_duplicate_ticket_total_increase: int,
    max_missing_summary_total_increase: int,
    max_missing_intent_total_increase: int,
    max_missing_tool_trace_total_increase: int,
    max_missing_error_code_total_increase: int,
    max_missing_reference_total_increase: int,
    max_missing_policy_version_total_increase: int,
    max_missing_tool_version_total_increase: int,
    max_unmasked_pii_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_pack_total = _safe_int(base_summary.get("pack_total"), 0)
    cur_pack_total = _safe_int(current_summary.get("pack_total"), 0)
    pack_total_drop = max(0, base_pack_total - cur_pack_total)
    if pack_total_drop > max(0, int(max_pack_total_drop)):
        failures.append(
            "pack_total regression: "
            f"baseline={base_pack_total}, current={cur_pack_total}, "
            f"allowed_drop={max(0, int(max_pack_total_drop))}"
        )

    baseline_increase_pairs = [
        ("duplicate_ticket_total", max_duplicate_ticket_total_increase),
        ("missing_summary_total", max_missing_summary_total_increase),
        ("missing_intent_total", max_missing_intent_total_increase),
        ("missing_tool_trace_total", max_missing_tool_trace_total_increase),
        ("missing_error_code_total", max_missing_error_code_total_increase),
        ("missing_reference_total", max_missing_reference_total_increase),
        ("missing_policy_version_total", max_missing_policy_version_total_increase),
        ("missing_tool_version_total", max_missing_tool_version_total_increase),
        ("unmasked_pii_total", max_unmasked_pii_total_increase),
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
    lines.append("# Chat Ticket Evidence Pack Schema")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- packs_jsonl: {payload.get('packs_jsonl')}")
    lines.append(f"- pack_total: {_safe_int(summary.get('pack_total'), 0)}")
    lines.append(f"- missing_summary_total: {_safe_int(summary.get('missing_summary_total'), 0)}")
    lines.append(f"- missing_intent_total: {_safe_int(summary.get('missing_intent_total'), 0)}")
    lines.append(f"- unmasked_pii_total: {_safe_int(summary.get('unmasked_pii_total'), 0)}")
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
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat ticket evidence pack schema quality.")
    parser.add_argument("--packs-jsonl", default="var/chat_ticket/evidence_packs.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_evidence_pack_schema")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-duplicate-ticket-total", type=int, default=0)
    parser.add_argument("--max-missing-summary-total", type=int, default=0)
    parser.add_argument("--max-missing-intent-total", type=int, default=0)
    parser.add_argument("--max-missing-tool-trace-total", type=int, default=0)
    parser.add_argument("--max-missing-error-code-total", type=int, default=0)
    parser.add_argument("--max-missing-reference-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-tool-version-total", type=int, default=0)
    parser.add_argument("--max-unmasked-pii-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-pack-total-drop", type=int, default=10)
    parser.add_argument("--max-duplicate-ticket-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-summary-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-intent-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-tool-trace-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-error-code-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reference-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-tool-version-total-increase", type=int, default=0)
    parser.add_argument("--max-unmasked-pii-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.packs_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_evidence_pack_schema(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_duplicate_ticket_total=max(0, int(args.max_duplicate_ticket_total)),
        max_missing_summary_total=max(0, int(args.max_missing_summary_total)),
        max_missing_intent_total=max(0, int(args.max_missing_intent_total)),
        max_missing_tool_trace_total=max(0, int(args.max_missing_tool_trace_total)),
        max_missing_error_code_total=max(0, int(args.max_missing_error_code_total)),
        max_missing_reference_total=max(0, int(args.max_missing_reference_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_tool_version_total=max(0, int(args.max_missing_tool_version_total)),
        max_unmasked_pii_total=max(0, int(args.max_unmasked_pii_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_pack_total_drop=max(0, int(args.max_pack_total_drop)),
            max_duplicate_ticket_total_increase=max(0, int(args.max_duplicate_ticket_total_increase)),
            max_missing_summary_total_increase=max(0, int(args.max_missing_summary_total_increase)),
            max_missing_intent_total_increase=max(0, int(args.max_missing_intent_total_increase)),
            max_missing_tool_trace_total_increase=max(0, int(args.max_missing_tool_trace_total_increase)),
            max_missing_error_code_total_increase=max(0, int(args.max_missing_error_code_total_increase)),
            max_missing_reference_total_increase=max(0, int(args.max_missing_reference_total_increase)),
            max_missing_policy_version_total_increase=max(0, int(args.max_missing_policy_version_total_increase)),
            max_missing_tool_version_total_increase=max(0, int(args.max_missing_tool_version_total_increase)),
            max_unmasked_pii_total_increase=max(0, int(args.max_unmasked_pii_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packs_jsonl": str(args.packs_jsonl),
        "source": {
            "packs_jsonl": str(args.packs_jsonl),
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
                "max_duplicate_ticket_total": int(args.max_duplicate_ticket_total),
                "max_missing_summary_total": int(args.max_missing_summary_total),
                "max_missing_intent_total": int(args.max_missing_intent_total),
                "max_missing_tool_trace_total": int(args.max_missing_tool_trace_total),
                "max_missing_error_code_total": int(args.max_missing_error_code_total),
                "max_missing_reference_total": int(args.max_missing_reference_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_tool_version_total": int(args.max_missing_tool_version_total),
                "max_unmasked_pii_total": int(args.max_unmasked_pii_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_pack_total_drop": int(args.max_pack_total_drop),
                "max_duplicate_ticket_total_increase": int(args.max_duplicate_ticket_total_increase),
                "max_missing_summary_total_increase": int(args.max_missing_summary_total_increase),
                "max_missing_intent_total_increase": int(args.max_missing_intent_total_increase),
                "max_missing_tool_trace_total_increase": int(args.max_missing_tool_trace_total_increase),
                "max_missing_error_code_total_increase": int(args.max_missing_error_code_total_increase),
                "max_missing_reference_total_increase": int(args.max_missing_reference_total_increase),
                "max_missing_policy_version_total_increase": int(args.max_missing_policy_version_total_increase),
                "max_missing_tool_version_total_increase": int(args.max_missing_tool_version_total_increase),
                "max_unmasked_pii_total_increase": int(args.max_unmasked_pii_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"pack_total={_safe_int(summary.get('pack_total'), 0)}")
    print(f"missing_summary_total={_safe_int(summary.get('missing_summary_total'), 0)}")
    print(f"unmasked_pii_total={_safe_int(summary.get('unmasked_pii_total'), 0)}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
