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


def _query_event(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("query_id") or row.get("session_query_id") or "").strip())


def _knowledge_hit(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("knowledge_hit"), False):
        return True
    return bool(str(row.get("knowledge_doc_id") or row.get("ticket_knowledge_id") or "").strip())


def _resolved(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("resolved"), False)


def _resolved_with_knowledge(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("resolved_with_knowledge"), False):
        return True
    return _resolved(row) and _knowledge_hit(row)


def _repeat_issue(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("repeat_issue"), False)


def _stale_knowledge_hit(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("stale_knowledge_hit"), False)


def _rollback_knowledge_hit(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("rollback_knowledge_hit"), False)


def _knowledge_conflict(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("knowledge_conflict"), False)


def summarize_ticket_knowledge_retrieval_impact_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    query_total = 0
    knowledge_hit_total = 0
    resolved_total = 0
    resolved_with_knowledge_total = 0
    repeat_issue_total = 0
    repeat_issue_resolved_total = 0
    stale_knowledge_hit_total = 0
    rollback_knowledge_hit_total = 0
    knowledge_conflict_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _query_event(row):
            continue
        query_total += 1

        knowledge_hit = _knowledge_hit(row)
        resolved = _resolved(row)
        resolved_with_knowledge = _resolved_with_knowledge(row)
        repeat_issue = _repeat_issue(row)

        if knowledge_hit:
            knowledge_hit_total += 1
        if resolved:
            resolved_total += 1
        if resolved_with_knowledge:
            resolved_with_knowledge_total += 1
        if repeat_issue:
            repeat_issue_total += 1
            if resolved:
                repeat_issue_resolved_total += 1
        if _stale_knowledge_hit(row):
            stale_knowledge_hit_total += 1
        if _rollback_knowledge_hit(row):
            rollback_knowledge_hit_total += 1
        if _knowledge_conflict(row):
            knowledge_conflict_total += 1

    knowledge_hit_ratio = 1.0 if query_total == 0 else float(knowledge_hit_total) / float(query_total)
    resolved_with_knowledge_ratio = (
        1.0 if resolved_total == 0 else float(resolved_with_knowledge_total) / float(resolved_total)
    )
    repeat_issue_resolution_ratio = (
        1.0 if repeat_issue_total == 0 else float(repeat_issue_resolved_total) / float(repeat_issue_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "query_total": query_total,
        "knowledge_hit_total": knowledge_hit_total,
        "knowledge_hit_ratio": knowledge_hit_ratio,
        "resolved_total": resolved_total,
        "resolved_with_knowledge_total": resolved_with_knowledge_total,
        "resolved_with_knowledge_ratio": resolved_with_knowledge_ratio,
        "repeat_issue_total": repeat_issue_total,
        "repeat_issue_resolved_total": repeat_issue_resolved_total,
        "repeat_issue_resolution_ratio": repeat_issue_resolution_ratio,
        "stale_knowledge_hit_total": stale_knowledge_hit_total,
        "rollback_knowledge_hit_total": rollback_knowledge_hit_total,
        "knowledge_conflict_total": knowledge_conflict_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_query_total: int,
    min_knowledge_hit_ratio: float,
    min_resolved_with_knowledge_ratio: float,
    min_repeat_issue_resolution_ratio: float,
    max_stale_knowledge_hit_total: int,
    max_rollback_knowledge_hit_total: int,
    max_knowledge_conflict_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    query_total = _safe_int(summary.get("query_total"), 0)
    knowledge_hit_ratio = _safe_float(summary.get("knowledge_hit_ratio"), 0.0)
    resolved_with_knowledge_ratio = _safe_float(summary.get("resolved_with_knowledge_ratio"), 0.0)
    repeat_issue_resolution_ratio = _safe_float(summary.get("repeat_issue_resolution_ratio"), 0.0)
    stale_knowledge_hit_total = _safe_int(summary.get("stale_knowledge_hit_total"), 0)
    rollback_knowledge_hit_total = _safe_int(summary.get("rollback_knowledge_hit_total"), 0)
    knowledge_conflict_total = _safe_int(summary.get("knowledge_conflict_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat ticket knowledge retrieval window too small: {window_size} < {int(min_window)}")
    if query_total < max(0, int(min_query_total)):
        failures.append(f"chat ticket knowledge retrieval query total too small: {query_total} < {int(min_query_total)}")
    if window_size == 0:
        return failures

    if knowledge_hit_ratio < max(0.0, float(min_knowledge_hit_ratio)):
        failures.append(
            f"chat ticket knowledge retrieval hit ratio below minimum: {knowledge_hit_ratio:.4f} < {float(min_knowledge_hit_ratio):.4f}"
        )
    if resolved_with_knowledge_ratio < max(0.0, float(min_resolved_with_knowledge_ratio)):
        failures.append(
            "chat ticket knowledge retrieval resolved-with-knowledge ratio below minimum: "
            f"{resolved_with_knowledge_ratio:.4f} < {float(min_resolved_with_knowledge_ratio):.4f}"
        )
    if repeat_issue_resolution_ratio < max(0.0, float(min_repeat_issue_resolution_ratio)):
        failures.append(
            "chat ticket knowledge retrieval repeat-issue resolution ratio below minimum: "
            f"{repeat_issue_resolution_ratio:.4f} < {float(min_repeat_issue_resolution_ratio):.4f}"
        )
    if stale_knowledge_hit_total > max(0, int(max_stale_knowledge_hit_total)):
        failures.append(
            f"chat ticket knowledge retrieval stale-knowledge hit total exceeded: {stale_knowledge_hit_total} > {int(max_stale_knowledge_hit_total)}"
        )
    if rollback_knowledge_hit_total > max(0, int(max_rollback_knowledge_hit_total)):
        failures.append(
            "chat ticket knowledge retrieval rollback-knowledge hit total exceeded: "
            f"{rollback_knowledge_hit_total} > {int(max_rollback_knowledge_hit_total)}"
        )
    if knowledge_conflict_total > max(0, int(max_knowledge_conflict_total)):
        failures.append(
            f"chat ticket knowledge retrieval conflict total exceeded: {knowledge_conflict_total} > {int(max_knowledge_conflict_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat ticket knowledge retrieval stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Knowledge Retrieval Impact Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- query_total: {_safe_int(summary.get('query_total'), 0)}")
    lines.append(f"- knowledge_hit_ratio: {_safe_float(summary.get('knowledge_hit_ratio'), 0.0):.4f}")
    lines.append(
        f"- resolved_with_knowledge_ratio: {_safe_float(summary.get('resolved_with_knowledge_ratio'), 0.0):.4f}"
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
    parser = argparse.ArgumentParser(description="Evaluate ticket knowledge retrieval integration impact.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket_knowledge/retrieval_integration_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_knowledge_retrieval_impact_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-query-total", type=int, default=0)
    parser.add_argument("--min-knowledge-hit-ratio", type=float, default=0.0)
    parser.add_argument("--min-resolved-with-knowledge-ratio", type=float, default=0.0)
    parser.add_argument("--min-repeat-issue-resolution-ratio", type=float, default=0.0)
    parser.add_argument("--max-stale-knowledge-hit-total", type=int, default=1000000)
    parser.add_argument("--max-rollback-knowledge-hit-total", type=int, default=1000000)
    parser.add_argument("--max-knowledge-conflict-total", type=int, default=1000000)
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
    summary = summarize_ticket_knowledge_retrieval_impact_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_query_total=max(0, int(args.min_query_total)),
        min_knowledge_hit_ratio=max(0.0, float(args.min_knowledge_hit_ratio)),
        min_resolved_with_knowledge_ratio=max(0.0, float(args.min_resolved_with_knowledge_ratio)),
        min_repeat_issue_resolution_ratio=max(0.0, float(args.min_repeat_issue_resolution_ratio)),
        max_stale_knowledge_hit_total=max(0, int(args.max_stale_knowledge_hit_total)),
        max_rollback_knowledge_hit_total=max(0, int(args.max_rollback_knowledge_hit_total)),
        max_knowledge_conflict_total=max(0, int(args.max_knowledge_conflict_total)),
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
                "min_query_total": int(args.min_query_total),
                "min_knowledge_hit_ratio": float(args.min_knowledge_hit_ratio),
                "min_resolved_with_knowledge_ratio": float(args.min_resolved_with_knowledge_ratio),
                "min_repeat_issue_resolution_ratio": float(args.min_repeat_issue_resolution_ratio),
                "max_stale_knowledge_hit_total": int(args.max_stale_knowledge_hit_total),
                "max_rollback_knowledge_hit_total": int(args.max_rollback_knowledge_hit_total),
                "max_knowledge_conflict_total": int(args.max_knowledge_conflict_total),
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
    print(f"query_total={_safe_int(summary.get('query_total'), 0)}")
    print(f"knowledge_hit_ratio={_safe_float(summary.get('knowledge_hit_ratio'), 0.0):.4f}")
    print(f"repeat_issue_resolution_ratio={_safe_float(summary.get('repeat_issue_resolution_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
