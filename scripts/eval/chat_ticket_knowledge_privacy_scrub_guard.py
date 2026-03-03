#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


SAFE_STORAGE_MODES = {"masked_raw", "hash_summary", "masked", "none"}


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


def _list_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, int(value))
    if isinstance(value, list):
        return len(value)
    text = str(value).strip()
    if not text:
        return 0
    if "," in text:
        return len([item for item in text.split(",") if item.strip()])
    return 1


def _candidate_event(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("candidate_generated"), False):
        return True
    return bool(str(row.get("candidate_id") or row.get("knowledge_candidate_id") or "").strip())


def _privacy_scrub_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("privacy_scrub_applied"), False):
        return True
    return _safe_bool(row.get("pii_scrubbed"), False)


def _pii_detected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("pii_detected"), False):
        return True
    return _list_count(row.get("pii_types")) > 0


def _pii_leak(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("pii_leak_detected"), False):
        return True
    return _safe_bool(row.get("pii_after_scrub"), False)


def _redaction_rule_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("redaction_rule_version") or row.get("scrub_policy_version") or "").strip())


def _retention_policy_present(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("retention_policy_applied"), False):
        return True
    return bool(str(row.get("retention_policy") or row.get("retention_mode") or "").strip())


def _safe_storage_mode(row: Mapping[str, Any]) -> bool:
    mode = str(row.get("message_storage_mode") or row.get("storage_mode") or "").strip().lower()
    if not mode:
        return True
    return mode in SAFE_STORAGE_MODES


def summarize_ticket_knowledge_privacy_scrub_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    candidate_total = 0
    scrubbed_total = 0
    pii_detected_total = 0
    pii_leak_total = 0
    redaction_rule_missing_total = 0
    retention_policy_missing_total = 0
    unsafe_storage_mode_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _candidate_event(row):
            continue
        candidate_total += 1

        scrubbed = _privacy_scrub_applied(row)
        pii_detected = _pii_detected(row)
        if scrubbed:
            scrubbed_total += 1
        if pii_detected:
            pii_detected_total += 1
        if pii_detected and _pii_leak(row):
            pii_leak_total += 1
        if pii_detected and scrubbed and not _redaction_rule_present(row):
            redaction_rule_missing_total += 1
        if not _retention_policy_present(row):
            retention_policy_missing_total += 1
        if not _safe_storage_mode(row):
            unsafe_storage_mode_total += 1

    scrub_coverage_ratio = 1.0 if candidate_total == 0 else float(scrubbed_total) / float(candidate_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "candidate_total": candidate_total,
        "scrubbed_total": scrubbed_total,
        "scrub_coverage_ratio": scrub_coverage_ratio,
        "pii_detected_total": pii_detected_total,
        "pii_leak_total": pii_leak_total,
        "redaction_rule_missing_total": redaction_rule_missing_total,
        "retention_policy_missing_total": retention_policy_missing_total,
        "unsafe_storage_mode_total": unsafe_storage_mode_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_candidate_total: int,
    min_scrub_coverage_ratio: float,
    max_pii_leak_total: int,
    max_redaction_rule_missing_total: int,
    max_retention_policy_missing_total: int,
    max_unsafe_storage_mode_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    candidate_total = _safe_int(summary.get("candidate_total"), 0)
    scrub_coverage_ratio = _safe_float(summary.get("scrub_coverage_ratio"), 0.0)
    pii_leak_total = _safe_int(summary.get("pii_leak_total"), 0)
    redaction_rule_missing_total = _safe_int(summary.get("redaction_rule_missing_total"), 0)
    retention_policy_missing_total = _safe_int(summary.get("retention_policy_missing_total"), 0)
    unsafe_storage_mode_total = _safe_int(summary.get("unsafe_storage_mode_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat ticket knowledge privacy window too small: {window_size} < {int(min_window)}")
    if candidate_total < max(0, int(min_candidate_total)):
        failures.append(
            f"chat ticket knowledge privacy candidate total too small: {candidate_total} < {int(min_candidate_total)}"
        )
    if window_size == 0:
        return failures

    if scrub_coverage_ratio < max(0.0, float(min_scrub_coverage_ratio)):
        failures.append(
            f"chat ticket knowledge privacy scrub coverage ratio below minimum: {scrub_coverage_ratio:.4f} < {float(min_scrub_coverage_ratio):.4f}"
        )
    if pii_leak_total > max(0, int(max_pii_leak_total)):
        failures.append(f"chat ticket knowledge privacy PII leak total exceeded: {pii_leak_total} > {int(max_pii_leak_total)}")
    if redaction_rule_missing_total > max(0, int(max_redaction_rule_missing_total)):
        failures.append(
            "chat ticket knowledge privacy redaction-rule missing total exceeded: "
            f"{redaction_rule_missing_total} > {int(max_redaction_rule_missing_total)}"
        )
    if retention_policy_missing_total > max(0, int(max_retention_policy_missing_total)):
        failures.append(
            "chat ticket knowledge privacy retention-policy missing total exceeded: "
            f"{retention_policy_missing_total} > {int(max_retention_policy_missing_total)}"
        )
    if unsafe_storage_mode_total > max(0, int(max_unsafe_storage_mode_total)):
        failures.append(
            "chat ticket knowledge privacy unsafe-storage mode total exceeded: "
            f"{unsafe_storage_mode_total} > {int(max_unsafe_storage_mode_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat ticket knowledge privacy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Knowledge Privacy Scrub Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- candidate_total: {_safe_int(summary.get('candidate_total'), 0)}")
    lines.append(f"- scrub_coverage_ratio: {_safe_float(summary.get('scrub_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- pii_leak_total: {_safe_int(summary.get('pii_leak_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate ticket-to-knowledge privacy scrub quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket_knowledge/privacy_scrub_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_knowledge_privacy_scrub_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-candidate-total", type=int, default=0)
    parser.add_argument("--min-scrub-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-pii-leak-total", type=int, default=1000000)
    parser.add_argument("--max-redaction-rule-missing-total", type=int, default=1000000)
    parser.add_argument("--max-retention-policy-missing-total", type=int, default=1000000)
    parser.add_argument("--max-unsafe-storage-mode-total", type=int, default=1000000)
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
    summary = summarize_ticket_knowledge_privacy_scrub_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_candidate_total=max(0, int(args.min_candidate_total)),
        min_scrub_coverage_ratio=max(0.0, float(args.min_scrub_coverage_ratio)),
        max_pii_leak_total=max(0, int(args.max_pii_leak_total)),
        max_redaction_rule_missing_total=max(0, int(args.max_redaction_rule_missing_total)),
        max_retention_policy_missing_total=max(0, int(args.max_retention_policy_missing_total)),
        max_unsafe_storage_mode_total=max(0, int(args.max_unsafe_storage_mode_total)),
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
                "min_candidate_total": int(args.min_candidate_total),
                "min_scrub_coverage_ratio": float(args.min_scrub_coverage_ratio),
                "max_pii_leak_total": int(args.max_pii_leak_total),
                "max_redaction_rule_missing_total": int(args.max_redaction_rule_missing_total),
                "max_retention_policy_missing_total": int(args.max_retention_policy_missing_total),
                "max_unsafe_storage_mode_total": int(args.max_unsafe_storage_mode_total),
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
    print(f"candidate_total={_safe_int(summary.get('candidate_total'), 0)}")
    print(f"scrub_coverage_ratio={_safe_float(summary.get('scrub_coverage_ratio'), 0.0):.4f}")
    print(f"pii_leak_total={_safe_int(summary.get('pii_leak_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
