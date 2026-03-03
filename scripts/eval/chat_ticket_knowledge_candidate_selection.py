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


def _ticket_closed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("ticket_closed"), False):
        return True
    status = str(row.get("ticket_status") or row.get("status") or "").strip().lower()
    return status in {"closed", "resolved", "done"}


def _candidate_generated(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("candidate_generated"), False):
        return True
    event_type = str(row.get("event_type") or "").strip().lower()
    if event_type in {"candidate_generated", "knowledge_candidate_created"}:
        return True
    return bool(str(row.get("candidate_id") or row.get("knowledge_candidate_id") or "").strip())


def _candidate_score(row: Mapping[str, Any]) -> float:
    return _safe_float(row.get("reusable_score") or row.get("candidate_score"), 0.0)


def _taxonomy_present(row: Mapping[str, Any]) -> bool:
    issue_type = str(row.get("issue_type") or row.get("problem_type") or "").strip()
    resolution_type = str(row.get("resolution_type") or row.get("resolution_pattern") or "").strip()
    return bool(issue_type and resolution_type)


def _provenance_present(row: Mapping[str, Any]) -> bool:
    ticket_id = str(row.get("ticket_id") or row.get("source_ticket_id") or "").strip()
    closed_at = _parse_ts(row.get("ticket_closed_at") or row.get("closed_at"))
    return bool(ticket_id and closed_at is not None)


def summarize_ticket_knowledge_candidate_selection(
    rows: list[Mapping[str, Any]],
    *,
    min_reusable_score: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    ticket_total = 0
    closed_ticket_total = 0
    candidate_total = 0
    invalid_status_candidate_total = 0
    low_confidence_candidate_total = 0
    candidate_taxonomy_missing_total = 0
    source_provenance_missing_total = 0

    for row in rows:
        ticket_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        closed = _ticket_closed(row)
        if closed:
            closed_ticket_total += 1

        if not _candidate_generated(row):
            continue
        candidate_total += 1

        if not closed:
            invalid_status_candidate_total += 1
        if _candidate_score(row) < max(0.0, float(min_reusable_score)):
            low_confidence_candidate_total += 1
        if not _taxonomy_present(row):
            candidate_taxonomy_missing_total += 1
        if not _provenance_present(row):
            source_provenance_missing_total += 1

    candidate_rate = 1.0 if closed_ticket_total == 0 else float(candidate_total) / float(closed_ticket_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "ticket_total": ticket_total,
        "closed_ticket_total": closed_ticket_total,
        "candidate_total": candidate_total,
        "candidate_rate": candidate_rate,
        "invalid_status_candidate_total": invalid_status_candidate_total,
        "low_confidence_candidate_total": low_confidence_candidate_total,
        "candidate_taxonomy_missing_total": candidate_taxonomy_missing_total,
        "source_provenance_missing_total": source_provenance_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_ticket_total: int,
    min_closed_ticket_total: int,
    min_candidate_total: int,
    min_candidate_rate: float,
    max_invalid_status_candidate_total: int,
    max_low_confidence_candidate_total: int,
    max_candidate_taxonomy_missing_total: int,
    max_source_provenance_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    ticket_total = _safe_int(summary.get("ticket_total"), 0)
    closed_ticket_total = _safe_int(summary.get("closed_ticket_total"), 0)
    candidate_total = _safe_int(summary.get("candidate_total"), 0)
    candidate_rate = _safe_float(summary.get("candidate_rate"), 0.0)
    invalid_status_candidate_total = _safe_int(summary.get("invalid_status_candidate_total"), 0)
    low_confidence_candidate_total = _safe_int(summary.get("low_confidence_candidate_total"), 0)
    candidate_taxonomy_missing_total = _safe_int(summary.get("candidate_taxonomy_missing_total"), 0)
    source_provenance_missing_total = _safe_int(summary.get("source_provenance_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat ticket knowledge candidate window too small: {window_size} < {int(min_window)}")
    if ticket_total < max(0, int(min_ticket_total)):
        failures.append(f"chat ticket knowledge ticket total too small: {ticket_total} < {int(min_ticket_total)}")
    if closed_ticket_total < max(0, int(min_closed_ticket_total)):
        failures.append(
            f"chat ticket knowledge closed ticket total too small: {closed_ticket_total} < {int(min_closed_ticket_total)}"
        )
    if candidate_total < max(0, int(min_candidate_total)):
        failures.append(
            f"chat ticket knowledge candidate total too small: {candidate_total} < {int(min_candidate_total)}"
        )
    if window_size == 0:
        return failures

    if candidate_rate < max(0.0, float(min_candidate_rate)):
        failures.append(
            f"chat ticket knowledge candidate rate below minimum: {candidate_rate:.4f} < {float(min_candidate_rate):.4f}"
        )
    if invalid_status_candidate_total > max(0, int(max_invalid_status_candidate_total)):
        failures.append(
            "chat ticket knowledge invalid-status candidate total exceeded: "
            f"{invalid_status_candidate_total} > {int(max_invalid_status_candidate_total)}"
        )
    if low_confidence_candidate_total > max(0, int(max_low_confidence_candidate_total)):
        failures.append(
            "chat ticket knowledge low-confidence candidate total exceeded: "
            f"{low_confidence_candidate_total} > {int(max_low_confidence_candidate_total)}"
        )
    if candidate_taxonomy_missing_total > max(0, int(max_candidate_taxonomy_missing_total)):
        failures.append(
            "chat ticket knowledge taxonomy missing total exceeded: "
            f"{candidate_taxonomy_missing_total} > {int(max_candidate_taxonomy_missing_total)}"
        )
    if source_provenance_missing_total > max(0, int(max_source_provenance_missing_total)):
        failures.append(
            "chat ticket knowledge provenance missing total exceeded: "
            f"{source_provenance_missing_total} > {int(max_source_provenance_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat ticket knowledge candidate stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Knowledge Candidate Selection")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- closed_ticket_total: {_safe_int(summary.get('closed_ticket_total'), 0)}")
    lines.append(f"- candidate_total: {_safe_int(summary.get('candidate_total'), 0)}")
    lines.append(f"- candidate_rate: {_safe_float(summary.get('candidate_rate'), 0.0):.4f}")
    lines.append(f"- invalid_status_candidate_total: {_safe_int(summary.get('invalid_status_candidate_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate ticket-to-knowledge candidate selection quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket_knowledge/candidate_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_knowledge_candidate_selection")
    parser.add_argument("--min-reusable-score", type=float, default=0.6)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-ticket-total", type=int, default=0)
    parser.add_argument("--min-closed-ticket-total", type=int, default=0)
    parser.add_argument("--min-candidate-total", type=int, default=0)
    parser.add_argument("--min-candidate-rate", type=float, default=0.0)
    parser.add_argument("--max-invalid-status-candidate-total", type=int, default=1000000)
    parser.add_argument("--max-low-confidence-candidate-total", type=int, default=1000000)
    parser.add_argument("--max-candidate-taxonomy-missing-total", type=int, default=1000000)
    parser.add_argument("--max-source-provenance-missing-total", type=int, default=1000000)
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
    summary = summarize_ticket_knowledge_candidate_selection(
        rows,
        min_reusable_score=max(0.0, float(args.min_reusable_score)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_ticket_total=max(0, int(args.min_ticket_total)),
        min_closed_ticket_total=max(0, int(args.min_closed_ticket_total)),
        min_candidate_total=max(0, int(args.min_candidate_total)),
        min_candidate_rate=max(0.0, float(args.min_candidate_rate)),
        max_invalid_status_candidate_total=max(0, int(args.max_invalid_status_candidate_total)),
        max_low_confidence_candidate_total=max(0, int(args.max_low_confidence_candidate_total)),
        max_candidate_taxonomy_missing_total=max(0, int(args.max_candidate_taxonomy_missing_total)),
        max_source_provenance_missing_total=max(0, int(args.max_source_provenance_missing_total)),
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
                "min_reusable_score": float(args.min_reusable_score),
                "min_window": int(args.min_window),
                "min_ticket_total": int(args.min_ticket_total),
                "min_closed_ticket_total": int(args.min_closed_ticket_total),
                "min_candidate_total": int(args.min_candidate_total),
                "min_candidate_rate": float(args.min_candidate_rate),
                "max_invalid_status_candidate_total": int(args.max_invalid_status_candidate_total),
                "max_low_confidence_candidate_total": int(args.max_low_confidence_candidate_total),
                "max_candidate_taxonomy_missing_total": int(args.max_candidate_taxonomy_missing_total),
                "max_source_provenance_missing_total": int(args.max_source_provenance_missing_total),
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
    print(f"closed_ticket_total={_safe_int(summary.get('closed_ticket_total'), 0)}")
    print(f"candidate_total={_safe_int(summary.get('candidate_total'), 0)}")
    print(f"candidate_rate={_safe_float(summary.get('candidate_rate'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
