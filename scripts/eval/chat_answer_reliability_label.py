#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_LEVELS = {"HIGH", "MEDIUM", "LOW"}
HIGH_CONFLICT = {"HIGH", "SEVERE", "CRITICAL"}
DEFINITIVE_PATTERNS = [
    r"\bdefinitely\b",
    r"\bguaranteed\b",
    r"\bconfirmed\b",
    r"\bcompleted\b",
    r"확정",
    r"무조건",
    r"반드시",
    r"확실히",
    r"완료되었습니다",
    r"조회했습니다",
]


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


def _normalize_level(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "H": "HIGH",
        "M": "MEDIUM",
        "L": "LOW",
        "SAFE": "HIGH",
        "WARN": "MEDIUM",
        "RISK": "LOW",
    }
    if text in VALID_LEVELS:
        return text
    return aliases.get(text, text)


def _derived_level(row: Mapping[str, Any]) -> str:
    trust_score = _safe_float(row.get("trust_score") or row.get("aggregate_trust_score"), 0.0)
    stale_ratio = _safe_float(row.get("stale_source_ratio"), 0.0)
    conflict = str(row.get("conflict_severity") or "").strip().upper()
    if trust_score >= 0.80 and stale_ratio <= 0.10 and conflict not in HIGH_CONFLICT:
        return "HIGH"
    if trust_score >= 0.55 and stale_ratio <= 0.40 and conflict not in HIGH_CONFLICT:
        return "MEDIUM"
    return "LOW"


def _has_definitive_claim(answer_text: str) -> bool:
    text = answer_text.strip()
    if not text:
        return False
    lowered = text.lower()
    for pattern in DEFINITIVE_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


def _has_guidance(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("guidance_provided"), False):
        return True
    for key in ("guidance_text", "followup_path", "fallback_action", "support_path", "next_step"):
        if str(row.get(key) or "").strip():
            return True
    return False


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


def summarize_reliability(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    answer_total = 0
    invalid_level_total = 0
    label_shift_total = 0
    high_total = 0
    medium_total = 0
    low_total = 0
    low_definitive_claim_total = 0
    low_missing_guidance_total = 0
    low_missing_reason_total = 0

    for row in events:
        answer_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        raw_level = _normalize_level(row.get("reliability_level"))
        derived_level = _derived_level(row)
        final_level = derived_level
        if raw_level:
            if raw_level in VALID_LEVELS:
                final_level = raw_level
            else:
                invalid_level_total += 1

        if raw_level in VALID_LEVELS and raw_level != derived_level:
            label_shift_total += 1

        if final_level == "HIGH":
            high_total += 1
        elif final_level == "MEDIUM":
            medium_total += 1
        else:
            low_total += 1
            answer_text = str(row.get("answer_text") or row.get("response_text") or "")
            if _has_definitive_claim(answer_text):
                low_definitive_claim_total += 1
            if not _has_guidance(row):
                low_missing_guidance_total += 1
            if not str(row.get("reason_code") or "").strip():
                low_missing_reason_total += 1

    label_shift_ratio = 0.0 if answer_total == 0 else float(label_shift_total) / float(answer_total)
    low_guardrail_coverage_ratio = 1.0
    if low_total > 0:
        violations = low_definitive_claim_total + low_missing_guidance_total
        low_guardrail_coverage_ratio = max(0.0, float(low_total - violations) / float(low_total))

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "answer_total": answer_total,
        "high_total": high_total,
        "medium_total": medium_total,
        "low_total": low_total,
        "invalid_level_total": invalid_level_total,
        "label_shift_total": label_shift_total,
        "label_shift_ratio": label_shift_ratio,
        "low_definitive_claim_total": low_definitive_claim_total,
        "low_missing_guidance_total": low_missing_guidance_total,
        "low_missing_reason_total": low_missing_reason_total,
        "low_guardrail_coverage_ratio": low_guardrail_coverage_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_invalid_level_total: int,
    max_label_shift_ratio: float,
    max_low_definitive_claim_total: int,
    max_low_missing_guidance_total: int,
    max_low_missing_reason_total: int,
    min_low_guardrail_coverage_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    invalid_level_total = _safe_int(summary.get("invalid_level_total"), 0)
    label_shift_ratio = _safe_float(summary.get("label_shift_ratio"), 0.0)
    low_definitive_claim_total = _safe_int(summary.get("low_definitive_claim_total"), 0)
    low_missing_guidance_total = _safe_int(summary.get("low_missing_guidance_total"), 0)
    low_missing_reason_total = _safe_int(summary.get("low_missing_reason_total"), 0)
    low_guardrail_coverage_ratio = _safe_float(summary.get("low_guardrail_coverage_ratio"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"answer reliability window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if invalid_level_total > max(0, int(max_invalid_level_total)):
        failures.append(f"invalid reliability label total exceeded: {invalid_level_total} > {int(max_invalid_level_total)}")
    if label_shift_ratio > max(0.0, float(max_label_shift_ratio)):
        failures.append(f"reliability label shift ratio exceeded: {label_shift_ratio:.4f} > {float(max_label_shift_ratio):.4f}")
    if low_definitive_claim_total > max(0, int(max_low_definitive_claim_total)):
        failures.append(
            "low reliability definitive claim total exceeded: "
            f"{low_definitive_claim_total} > {int(max_low_definitive_claim_total)}"
        )
    if low_missing_guidance_total > max(0, int(max_low_missing_guidance_total)):
        failures.append(
            "low reliability missing guidance total exceeded: "
            f"{low_missing_guidance_total} > {int(max_low_missing_guidance_total)}"
        )
    if low_missing_reason_total > max(0, int(max_low_missing_reason_total)):
        failures.append(
            f"low reliability missing reason total exceeded: {low_missing_reason_total} > {int(max_low_missing_reason_total)}"
        )
    if low_guardrail_coverage_ratio < max(0.0, float(min_low_guardrail_coverage_ratio)):
        failures.append(
            "low reliability guardrail coverage below threshold: "
            f"{low_guardrail_coverage_ratio:.4f} < {float(min_low_guardrail_coverage_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"answer reliability events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Answer Reliability Label")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- high_total: {_safe_int(summary.get('high_total'), 0)}")
    lines.append(f"- medium_total: {_safe_int(summary.get('medium_total'), 0)}")
    lines.append(f"- low_total: {_safe_int(summary.get('low_total'), 0)}")
    lines.append(f"- invalid_level_total: {_safe_int(summary.get('invalid_level_total'), 0)}")
    lines.append(f"- low_definitive_claim_total: {_safe_int(summary.get('low_definitive_claim_total'), 0)}")
    lines.append(f"- low_missing_guidance_total: {_safe_int(summary.get('low_missing_guidance_total'), 0)}")
    lines.append(f"- low_guardrail_coverage_ratio: {_safe_float(summary.get('low_guardrail_coverage_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate answer reliability labels and LOW guardrail compliance.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/answer_reliability_audit.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_answer_reliability_label")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-invalid-level-total", type=int, default=0)
    parser.add_argument("--max-label-shift-ratio", type=float, default=0.10)
    parser.add_argument("--max-low-definitive-claim-total", type=int, default=0)
    parser.add_argument("--max-low-missing-guidance-total", type=int, default=0)
    parser.add_argument("--max-low-missing-reason-total", type=int, default=0)
    parser.add_argument("--min-low-guardrail-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
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
    summary = summarize_reliability(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_invalid_level_total=max(0, int(args.max_invalid_level_total)),
        max_label_shift_ratio=max(0.0, float(args.max_label_shift_ratio)),
        max_low_definitive_claim_total=max(0, int(args.max_low_definitive_claim_total)),
        max_low_missing_guidance_total=max(0, int(args.max_low_missing_guidance_total)),
        max_low_missing_reason_total=max(0, int(args.max_low_missing_reason_total)),
        min_low_guardrail_coverage_ratio=max(0.0, float(args.min_low_guardrail_coverage_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
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
                "max_invalid_level_total": int(args.max_invalid_level_total),
                "max_label_shift_ratio": float(args.max_label_shift_ratio),
                "max_low_definitive_claim_total": int(args.max_low_definitive_claim_total),
                "max_low_missing_guidance_total": int(args.max_low_missing_guidance_total),
                "max_low_missing_reason_total": int(args.max_low_missing_reason_total),
                "min_low_guardrail_coverage_ratio": float(args.min_low_guardrail_coverage_ratio),
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
    print(f"answer_total={_safe_int(summary.get('answer_total'), 0)}")
    print(f"low_total={_safe_int(summary.get('low_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
