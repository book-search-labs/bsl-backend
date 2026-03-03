#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
SAFE_DECISIONS = {"ABSTAIN", "ESCALATE", "HUMAN_HANDOFF", "DEFER"}
UNSAFE_DECISIONS = {"ANSWER", "EXECUTE", "PROCEED"}
STANDARD_KO_PHRASES = ("정보가 상충", "확인이 필요", "공식 안내", "정확한 확인")
URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


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


def _normalize_severity(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"L": "LOW", "M": "MEDIUM", "H": "HIGH"}
    if text in VALID_SEVERITIES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_decision(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"BLOCK": "ABSTAIN", "HANDOFF": "HUMAN_HANDOFF"}
    return aliases.get(text, text or "UNKNOWN")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return []


def _should_abstain(row: Mapping[str, Any], severity: str) -> bool:
    if _safe_bool(row.get("should_abstain"), False):
        return True
    unresolved = _safe_bool(row.get("conflict_unresolved"), False) or str(row.get("status") or "").strip().upper() in {
        "UNRESOLVED",
        "PENDING_CONFIRMATION",
    }
    return severity == "HIGH" or unresolved


def _has_standard_phrase(message: str) -> bool:
    if not message:
        return False
    return any(phrase in message for phrase in STANDARD_KO_PHRASES)


def _has_source_link(row: Mapping[str, Any], message: str) -> bool:
    if _as_list(row.get("source_links")):
        return True
    if _as_list(row.get("citations")):
        return True
    return URL_RE.search(message or "") is not None


def summarize_safe_abstention(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    should_abstain_total = 0
    abstain_total = 0
    unsafe_definitive_total = 0
    missing_standard_phrase_total = 0
    missing_source_link_total = 0
    missing_reason_code_total = 0
    high_conflict_total = 0
    with_standard_and_source_total = 0

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        severity = _normalize_severity(row.get("conflict_severity") or row.get("severity"))
        decision = _normalize_decision(row.get("decision") or row.get("action"))
        message = str(row.get("response_text") or row.get("assistant_message") or "").strip()

        if severity == "HIGH":
            high_conflict_total += 1

        if not _should_abstain(row, severity):
            continue
        should_abstain_total += 1

        is_abstain = decision in SAFE_DECISIONS or _safe_bool(row.get("abstained"), False)
        if is_abstain:
            abstain_total += 1

        definitive_claim = _safe_bool(row.get("definitive_claim"), False)
        if decision in UNSAFE_DECISIONS or definitive_claim:
            unsafe_definitive_total += 1

        has_standard_phrase = _has_standard_phrase(message)
        has_source_link = _has_source_link(row, message)
        if not has_standard_phrase:
            missing_standard_phrase_total += 1
        if not has_source_link:
            missing_source_link_total += 1
        if has_standard_phrase and has_source_link:
            with_standard_and_source_total += 1

        if not str(row.get("reason_code") or "").strip():
            missing_reason_code_total += 1

    abstain_compliance_ratio = 1.0 if should_abstain_total == 0 else float(abstain_total) / float(should_abstain_total)
    message_quality_ratio = (
        1.0 if should_abstain_total == 0 else float(with_standard_and_source_total) / float(should_abstain_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "high_conflict_total": high_conflict_total,
        "should_abstain_total": should_abstain_total,
        "abstain_total": abstain_total,
        "abstain_compliance_ratio": abstain_compliance_ratio,
        "unsafe_definitive_total": unsafe_definitive_total,
        "missing_standard_phrase_total": missing_standard_phrase_total,
        "missing_source_link_total": missing_source_link_total,
        "missing_reason_code_total": missing_reason_code_total,
        "message_quality_ratio": message_quality_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_unsafe_definitive_total: int,
    min_abstain_compliance_ratio: float,
    max_missing_standard_phrase_total: int,
    max_missing_source_link_total: int,
    max_missing_reason_code_total: int,
    min_message_quality_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    unsafe_definitive_total = _safe_int(summary.get("unsafe_definitive_total"), 0)
    abstain_compliance_ratio = _safe_float(summary.get("abstain_compliance_ratio"), 1.0)
    missing_standard_phrase_total = _safe_int(summary.get("missing_standard_phrase_total"), 0)
    missing_source_link_total = _safe_int(summary.get("missing_source_link_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    message_quality_ratio = _safe_float(summary.get("message_quality_ratio"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"source conflict abstention window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if unsafe_definitive_total > max(0, int(max_unsafe_definitive_total)):
        failures.append(
            f"source conflict unsafe definitive total exceeded: {unsafe_definitive_total} > {int(max_unsafe_definitive_total)}"
        )
    if abstain_compliance_ratio < max(0.0, float(min_abstain_compliance_ratio)):
        failures.append(
            "source conflict abstain compliance ratio below threshold: "
            f"{abstain_compliance_ratio:.4f} < {float(min_abstain_compliance_ratio):.4f}"
        )
    if missing_standard_phrase_total > max(0, int(max_missing_standard_phrase_total)):
        failures.append(
            "source conflict missing standard phrase total exceeded: "
            f"{missing_standard_phrase_total} > {int(max_missing_standard_phrase_total)}"
        )
    if missing_source_link_total > max(0, int(max_missing_source_link_total)):
        failures.append(
            f"source conflict missing source link total exceeded: {missing_source_link_total} > {int(max_missing_source_link_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"source conflict missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if message_quality_ratio < max(0.0, float(min_message_quality_ratio)):
        failures.append(
            f"source conflict message quality ratio below threshold: {message_quality_ratio:.4f} < {float(min_message_quality_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"source conflict abstention stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Source Conflict Safe Abstention")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- should_abstain_total: {_safe_int(summary.get('should_abstain_total'), 0)}")
    lines.append(f"- abstain_compliance_ratio: {_safe_float(summary.get('abstain_compliance_ratio'), 1.0):.4f}")
    lines.append(f"- unsafe_definitive_total: {_safe_int(summary.get('unsafe_definitive_total'), 0)}")
    lines.append(f"- message_quality_ratio: {_safe_float(summary.get('message_quality_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate safe abstention messaging for source conflicts.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/source_conflict_user_messages.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_source_conflict_safe_abstention")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-unsafe-definitive-total", type=int, default=0)
    parser.add_argument("--min-abstain-compliance-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-standard-phrase-total", type=int, default=0)
    parser.add_argument("--max-missing-source-link-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--min-message-quality-ratio", type=float, default=0.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_safe_abstention(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_unsafe_definitive_total=max(0, int(args.max_unsafe_definitive_total)),
        min_abstain_compliance_ratio=max(0.0, float(args.min_abstain_compliance_ratio)),
        max_missing_standard_phrase_total=max(0, int(args.max_missing_standard_phrase_total)),
        max_missing_source_link_total=max(0, int(args.max_missing_source_link_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        min_message_quality_ratio=max(0.0, float(args.min_message_quality_ratio)),
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
                "max_unsafe_definitive_total": int(args.max_unsafe_definitive_total),
                "min_abstain_compliance_ratio": float(args.min_abstain_compliance_ratio),
                "max_missing_standard_phrase_total": int(args.max_missing_standard_phrase_total),
                "max_missing_source_link_total": int(args.max_missing_source_link_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "min_message_quality_ratio": float(args.min_message_quality_ratio),
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
    print(f"should_abstain_total={_safe_int(summary.get('should_abstain_total'), 0)}")
    print(f"unsafe_definitive_total={_safe_int(summary.get('unsafe_definitive_total'), 0)}")
    print(f"abstain_compliance_ratio={_safe_float(summary.get('abstain_compliance_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
