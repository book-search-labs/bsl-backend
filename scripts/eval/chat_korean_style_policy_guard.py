#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

POLITE_ENDING_RE = re.compile(r"(니다\.?|요\.?|해주세요\.?|하십시오\.?)$")


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


def _style_checked(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("style_checked"), False):
        return True
    return "style_score" in row or "style_policy_version" in row


def _politeness_violation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("politeness_violation"), False):
        return True
    text = str(row.get("response_text") or "").strip()
    if not text:
        return False
    if not _safe_bool(row.get("formal_required"), True):
        return False
    # Sentence-final politeness heuristic for Korean responses.
    last_sentence = re.split(r"[.!?]\s*", text)[0].strip()
    return POLITE_ENDING_RE.search(last_sentence) is None


def _sentence_length_violation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("sentence_length_violation"), False):
        return True
    limit = _safe_int(row.get("max_sentence_chars"), 120)
    text = str(row.get("response_text") or "").strip()
    if not text:
        return False
    sentences = [part.strip() for part in re.split(r"[.!?]\s*", text) if part.strip()]
    return any(len(sentence) > max(20, limit) for sentence in sentences)


def _numeric_format_violation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("numeric_format_violation"), False):
        return True
    return _safe_bool(row.get("number_style_violation"), False)


def _tone_violation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("tone_violation"), False):
        return True
    mode = str(row.get("tone_mode") or row.get("response_mode") or "").strip().lower()
    if not mode:
        return False
    text = str(row.get("response_text") or "").strip()
    if not text:
        return False
    if mode == "apology" and "죄송" not in text and "불편" not in text:
        return True
    if mode == "restriction" and "제한" not in text and "불가" not in text:
        return True
    return False


def summarize_korean_style_policy_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    response_total = 0
    style_checked_total = 0
    style_bypass_total = 0
    style_violation_total = 0
    politeness_violation_total = 0
    sentence_length_violation_total = 0
    numeric_format_violation_total = 0
    tone_violation_total = 0

    for row in rows:
        response_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        checked = _style_checked(row)
        if checked:
            style_checked_total += 1
        else:
            style_bypass_total += 1

        polite_violation = _politeness_violation(row)
        sentence_violation = _sentence_length_violation(row)
        numeric_violation = _numeric_format_violation(row)
        tone_violation = _tone_violation(row)

        if polite_violation:
            politeness_violation_total += 1
        if sentence_violation:
            sentence_length_violation_total += 1
        if numeric_violation:
            numeric_format_violation_total += 1
        if tone_violation:
            tone_violation_total += 1

        if polite_violation or sentence_violation or numeric_violation or tone_violation:
            style_violation_total += 1

    style_checked_ratio = 1.0 if response_total == 0 else float(style_checked_total) / float(response_total)
    style_compliance_ratio = 1.0 if style_checked_total == 0 else float(style_checked_total - style_violation_total) / float(
        style_checked_total
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "response_total": response_total,
        "style_checked_total": style_checked_total,
        "style_checked_ratio": style_checked_ratio,
        "style_bypass_total": style_bypass_total,
        "style_violation_total": style_violation_total,
        "style_compliance_ratio": style_compliance_ratio,
        "politeness_violation_total": politeness_violation_total,
        "sentence_length_violation_total": sentence_length_violation_total,
        "numeric_format_violation_total": numeric_format_violation_total,
        "tone_violation_total": tone_violation_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_response_total: int,
    min_style_checked_ratio: float,
    min_style_compliance_ratio: float,
    max_style_bypass_total: int,
    max_politeness_violation_total: int,
    max_sentence_length_violation_total: int,
    max_numeric_format_violation_total: int,
    max_tone_violation_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    response_total = _safe_int(summary.get("response_total"), 0)
    style_checked_ratio = _safe_float(summary.get("style_checked_ratio"), 0.0)
    style_compliance_ratio = _safe_float(summary.get("style_compliance_ratio"), 0.0)
    style_bypass_total = _safe_int(summary.get("style_bypass_total"), 0)
    politeness_violation_total = _safe_int(summary.get("politeness_violation_total"), 0)
    sentence_length_violation_total = _safe_int(summary.get("sentence_length_violation_total"), 0)
    numeric_format_violation_total = _safe_int(summary.get("numeric_format_violation_total"), 0)
    tone_violation_total = _safe_int(summary.get("tone_violation_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat korean style window too small: {window_size} < {int(min_window)}")
    if response_total < max(0, int(min_response_total)):
        failures.append(f"chat korean style response total too small: {response_total} < {int(min_response_total)}")
    if window_size == 0:
        return failures

    if style_checked_ratio < max(0.0, float(min_style_checked_ratio)):
        failures.append(
            f"chat korean style checked ratio below minimum: {style_checked_ratio:.4f} < {float(min_style_checked_ratio):.4f}"
        )
    if style_compliance_ratio < max(0.0, float(min_style_compliance_ratio)):
        failures.append(
            f"chat korean style compliance ratio below minimum: {style_compliance_ratio:.4f} < {float(min_style_compliance_ratio):.4f}"
        )
    if style_bypass_total > max(0, int(max_style_bypass_total)):
        failures.append(f"chat korean style bypass total exceeded: {style_bypass_total} > {int(max_style_bypass_total)}")
    if politeness_violation_total > max(0, int(max_politeness_violation_total)):
        failures.append(
            f"chat korean style politeness violation total exceeded: {politeness_violation_total} > {int(max_politeness_violation_total)}"
        )
    if sentence_length_violation_total > max(0, int(max_sentence_length_violation_total)):
        failures.append(
            "chat korean style sentence length violation total exceeded: "
            f"{sentence_length_violation_total} > {int(max_sentence_length_violation_total)}"
        )
    if numeric_format_violation_total > max(0, int(max_numeric_format_violation_total)):
        failures.append(
            "chat korean style numeric format violation total exceeded: "
            f"{numeric_format_violation_total} > {int(max_numeric_format_violation_total)}"
        )
    if tone_violation_total > max(0, int(max_tone_violation_total)):
        failures.append(f"chat korean style tone violation total exceeded: {tone_violation_total} > {int(max_tone_violation_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat korean style stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Style Policy Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- response_total: {_safe_int(summary.get('response_total'), 0)}")
    lines.append(f"- style_checked_ratio: {_safe_float(summary.get('style_checked_ratio'), 0.0):.4f}")
    lines.append(f"- style_compliance_ratio: {_safe_float(summary.get('style_compliance_ratio'), 0.0):.4f}")
    lines.append(f"- politeness_violation_total: {_safe_int(summary.get('politeness_violation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat korean style policy quality.")
    parser.add_argument("--events-jsonl", default="var/chat_style/style_policy_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_style_policy_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-response-total", type=int, default=0)
    parser.add_argument("--min-style-checked-ratio", type=float, default=0.0)
    parser.add_argument("--min-style-compliance-ratio", type=float, default=0.0)
    parser.add_argument("--max-style-bypass-total", type=int, default=0)
    parser.add_argument("--max-politeness-violation-total", type=int, default=0)
    parser.add_argument("--max-sentence-length-violation-total", type=int, default=0)
    parser.add_argument("--max-numeric-format-violation-total", type=int, default=0)
    parser.add_argument("--max-tone-violation-total", type=int, default=0)
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
    summary = summarize_korean_style_policy_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_response_total=max(0, int(args.min_response_total)),
        min_style_checked_ratio=max(0.0, float(args.min_style_checked_ratio)),
        min_style_compliance_ratio=max(0.0, float(args.min_style_compliance_ratio)),
        max_style_bypass_total=max(0, int(args.max_style_bypass_total)),
        max_politeness_violation_total=max(0, int(args.max_politeness_violation_total)),
        max_sentence_length_violation_total=max(0, int(args.max_sentence_length_violation_total)),
        max_numeric_format_violation_total=max(0, int(args.max_numeric_format_violation_total)),
        max_tone_violation_total=max(0, int(args.max_tone_violation_total)),
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
                "min_response_total": int(args.min_response_total),
                "min_style_checked_ratio": float(args.min_style_checked_ratio),
                "min_style_compliance_ratio": float(args.min_style_compliance_ratio),
                "max_style_bypass_total": int(args.max_style_bypass_total),
                "max_politeness_violation_total": int(args.max_politeness_violation_total),
                "max_sentence_length_violation_total": int(args.max_sentence_length_violation_total),
                "max_numeric_format_violation_total": int(args.max_numeric_format_violation_total),
                "max_tone_violation_total": int(args.max_tone_violation_total),
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
    print(f"response_total={_safe_int(summary.get('response_total'), 0)}")
    print(f"style_violation_total={_safe_int(summary.get('style_violation_total'), 0)}")
    print(f"style_compliance_ratio={_safe_float(summary.get('style_compliance_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
