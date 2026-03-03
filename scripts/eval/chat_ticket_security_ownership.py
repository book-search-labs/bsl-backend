#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?\d{3,4}[-\s]?\d{4})")


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "ticket_status_lookup": "TICKET_LOOKUP",
        "ticket_list_lookup": "TICKET_LOOKUP",
        "status_lookup": "TICKET_LOOKUP",
        "list_lookup": "TICKET_LOOKUP",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "ok": "OK",
        "success": "OK",
        "found": "OK",
        "forbidden": "FORBIDDEN",
        "denied": "FORBIDDEN",
        "error": "ERROR",
        "fail": "ERROR",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _contains_unmasked_pii(row: Mapping[str, Any]) -> bool:
    texts = [
        str(row.get("response_text") or ""),
        str(row.get("message") or ""),
        str(row.get("ticket_summary") or ""),
        str(row.get("attachment_label") or ""),
    ]
    merged = " ".join(texts)
    if "***" in merged or "masked" in merged.lower() or "redacted" in merged.lower():
        return False
    if EMAIL_RE.search(merged):
        return True
    for match in PHONE_RE.finditer(merged):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 10:
            return True
    return False


def _has_unmasked_attachment_url(row: Mapping[str, Any]) -> bool:
    url = str(row.get("attachment_url") or row.get("file_url") or "").strip()
    if not url:
        return False
    lowered = url.lower()
    if "masked" in lowered or "redacted" in lowered or "***" in url:
        return False
    return lowered.startswith("http://") or lowered.startswith("https://")


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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def summarize_security_ownership(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    lookup_total = 0
    authz_denied_total = 0
    lookup_error_total = 0
    ownership_violation_total = 0
    missing_owner_check_total = 0
    pii_unmasked_total = 0
    attachment_unmasked_link_total = 0

    for row in events:
        event = _normalize_event(row.get("event_type") or row.get("event") or row.get("status_event"))
        if event != "TICKET_LOOKUP":
            continue
        lookup_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        result = _normalize_result(row.get("result") or row.get("lookup_result"))
        owner_match = row.get("owner_match")
        if result == "FORBIDDEN":
            authz_denied_total += 1
        elif result == "ERROR":
            lookup_error_total += 1
        elif result == "OK":
            if owner_match is None:
                missing_owner_check_total += 1
            elif not _safe_bool(owner_match, False):
                ownership_violation_total += 1
            if _contains_unmasked_pii(row):
                pii_unmasked_total += 1
            if _has_unmasked_attachment_url(row):
                attachment_unmasked_link_total += 1

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "lookup_total": lookup_total,
        "authz_denied_total": authz_denied_total,
        "lookup_error_total": lookup_error_total,
        "ownership_violation_total": ownership_violation_total,
        "missing_owner_check_total": missing_owner_check_total,
        "pii_unmasked_total": pii_unmasked_total,
        "attachment_unmasked_link_total": attachment_unmasked_link_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_ownership_violation_total: int,
    max_missing_owner_check_total: int,
    max_pii_unmasked_total: int,
    max_attachment_unmasked_link_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    ownership_violation_total = _safe_int(summary.get("ownership_violation_total"), 0)
    missing_owner_check_total = _safe_int(summary.get("missing_owner_check_total"), 0)
    pii_unmasked_total = _safe_int(summary.get("pii_unmasked_total"), 0)
    attachment_unmasked_link_total = _safe_int(summary.get("attachment_unmasked_link_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket security window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if ownership_violation_total > max(0, int(max_ownership_violation_total)):
        failures.append(
            f"ticket ownership violation total exceeded: {ownership_violation_total} > {int(max_ownership_violation_total)}"
        )
    if missing_owner_check_total > max(0, int(max_missing_owner_check_total)):
        failures.append(
            f"ticket owner-check missing total exceeded: {missing_owner_check_total} > {int(max_missing_owner_check_total)}"
        )
    if pii_unmasked_total > max(0, int(max_pii_unmasked_total)):
        failures.append(f"ticket pii unmasked total exceeded: {pii_unmasked_total} > {int(max_pii_unmasked_total)}")
    if attachment_unmasked_link_total > max(0, int(max_attachment_unmasked_link_total)):
        failures.append(
            "ticket attachment unmasked link total exceeded: "
            f"{attachment_unmasked_link_total} > {int(max_attachment_unmasked_link_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket security events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_ownership_violation_total_increase: int,
    max_missing_owner_check_total_increase: int,
    max_pii_unmasked_total_increase: int,
    max_attachment_unmasked_link_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_ownership_violation_total = _safe_int(base_summary.get("ownership_violation_total"), 0)
    cur_ownership_violation_total = _safe_int(current_summary.get("ownership_violation_total"), 0)
    ownership_violation_total_increase = max(0, cur_ownership_violation_total - base_ownership_violation_total)
    if ownership_violation_total_increase > max(0, int(max_ownership_violation_total_increase)):
        failures.append(
            "ownership violation total regression: "
            f"baseline={base_ownership_violation_total}, current={cur_ownership_violation_total}, "
            f"allowed_increase={max(0, int(max_ownership_violation_total_increase))}"
        )

    base_missing_owner_check_total = _safe_int(base_summary.get("missing_owner_check_total"), 0)
    cur_missing_owner_check_total = _safe_int(current_summary.get("missing_owner_check_total"), 0)
    missing_owner_check_total_increase = max(0, cur_missing_owner_check_total - base_missing_owner_check_total)
    if missing_owner_check_total_increase > max(0, int(max_missing_owner_check_total_increase)):
        failures.append(
            "missing owner-check total regression: "
            f"baseline={base_missing_owner_check_total}, current={cur_missing_owner_check_total}, "
            f"allowed_increase={max(0, int(max_missing_owner_check_total_increase))}"
        )

    base_pii_unmasked_total = _safe_int(base_summary.get("pii_unmasked_total"), 0)
    cur_pii_unmasked_total = _safe_int(current_summary.get("pii_unmasked_total"), 0)
    pii_unmasked_total_increase = max(0, cur_pii_unmasked_total - base_pii_unmasked_total)
    if pii_unmasked_total_increase > max(0, int(max_pii_unmasked_total_increase)):
        failures.append(
            "pii unmasked total regression: "
            f"baseline={base_pii_unmasked_total}, current={cur_pii_unmasked_total}, "
            f"allowed_increase={max(0, int(max_pii_unmasked_total_increase))}"
        )

    base_attachment_unmasked_link_total = _safe_int(base_summary.get("attachment_unmasked_link_total"), 0)
    cur_attachment_unmasked_link_total = _safe_int(current_summary.get("attachment_unmasked_link_total"), 0)
    attachment_unmasked_link_total_increase = max(
        0,
        cur_attachment_unmasked_link_total - base_attachment_unmasked_link_total,
    )
    if attachment_unmasked_link_total_increase > max(0, int(max_attachment_unmasked_link_total_increase)):
        failures.append(
            "attachment unmasked link total regression: "
            f"baseline={base_attachment_unmasked_link_total}, current={cur_attachment_unmasked_link_total}, "
            f"allowed_increase={max(0, int(max_attachment_unmasked_link_total_increase))}"
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
    lines.append("# Chat Ticket Security Ownership")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- lookup_total: {_safe_int(summary.get('lookup_total'), 0)}")
    lines.append(f"- authz_denied_total: {_safe_int(summary.get('authz_denied_total'), 0)}")
    lines.append(f"- ownership_violation_total: {_safe_int(summary.get('ownership_violation_total'), 0)}")
    lines.append(f"- pii_unmasked_total: {_safe_int(summary.get('pii_unmasked_total'), 0)}")
    lines.append(f"- attachment_unmasked_link_total: {_safe_int(summary.get('attachment_unmasked_link_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate ticket ownership and security guardrails.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket/ticket_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_security_ownership")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-ownership-violation-total", type=int, default=0)
    parser.add_argument("--max-missing-owner-check-total", type=int, default=0)
    parser.add_argument("--max-pii-unmasked-total", type=int, default=0)
    parser.add_argument("--max-attachment-unmasked-link-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-ownership-violation-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-owner-check-total-increase", type=int, default=0)
    parser.add_argument("--max-pii-unmasked-total-increase", type=int, default=0)
    parser.add_argument("--max-attachment-unmasked-link-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
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
    summary = summarize_security_ownership(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_ownership_violation_total=max(0, int(args.max_ownership_violation_total)),
        max_missing_owner_check_total=max(0, int(args.max_missing_owner_check_total)),
        max_pii_unmasked_total=max(0, int(args.max_pii_unmasked_total)),
        max_attachment_unmasked_link_total=max(0, int(args.max_attachment_unmasked_link_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_ownership_violation_total_increase=max(0, int(args.max_ownership_violation_total_increase)),
            max_missing_owner_check_total_increase=max(0, int(args.max_missing_owner_check_total_increase)),
            max_pii_unmasked_total_increase=max(0, int(args.max_pii_unmasked_total_increase)),
            max_attachment_unmasked_link_total_increase=max(0, int(args.max_attachment_unmasked_link_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
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
                "max_ownership_violation_total": int(args.max_ownership_violation_total),
                "max_missing_owner_check_total": int(args.max_missing_owner_check_total),
                "max_pii_unmasked_total": int(args.max_pii_unmasked_total),
                "max_attachment_unmasked_link_total": int(args.max_attachment_unmasked_link_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_ownership_violation_total_increase": int(args.max_ownership_violation_total_increase),
                "max_missing_owner_check_total_increase": int(args.max_missing_owner_check_total_increase),
                "max_pii_unmasked_total_increase": int(args.max_pii_unmasked_total_increase),
                "max_attachment_unmasked_link_total_increase": int(args.max_attachment_unmasked_link_total_increase),
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
    print(f"lookup_total={_safe_int(summary.get('lookup_total'), 0)}")
    print(f"authz_denied_total={_safe_int(summary.get('authz_denied_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
