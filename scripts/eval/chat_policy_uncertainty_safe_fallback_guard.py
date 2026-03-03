#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


DEFINITIVE_PHRASES = (
    "확정",
    "무조건",
    "반드시",
    "즉시 처리",
    "처리 완료",
    "100%",
    "absolutely",
    "guaranteed",
)

SAFE_GUIDANCE_HINTS = (
    "확인이 필요",
    "정책 확인",
    "고객센터",
    "상담",
    "문의",
    "추가 정보",
    "확인 후",
    "안전하게 안내",
)

UNCERTAINTY_REASON_TOKENS = (
    "POLICY_UNCERTAIN",
    "LOW_EVIDENCE",
    "FALLBACK",
    "INSUFFICIENT_EVIDENCE",
)

DOWNGRADED_STATUSES = {
    "insufficient_evidence",
    "degraded",
    "safe_fallback",
}

DOWNGRADED_ACTIONS = {
    "OPEN_SUPPORT_TICKET",
    "PROVIDE_REQUIRED_INFO",
    "REFINE_QUERY",
    "RETRY",
}


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


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _answer_text(row: Mapping[str, Any]) -> str:
    return str(row.get("answer_text") or row.get("response_text") or row.get("output_text") or "").strip()


def _reason_code_text(row: Mapping[str, Any]) -> str:
    reason = row.get("reason_code")
    if isinstance(reason, list):
        return " ".join(str(item) for item in reason)
    return str(reason or row.get("reason_codes") or row.get("violation_codes") or "")


def _policy_uncertain(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("policy_uncertain"))
    if explicit is not None:
        return explicit
    if _safe_bool(row.get("insufficient_evidence")) is True:
        return True
    reason_text = _reason_code_text(row).upper()
    if any(token in reason_text for token in UNCERTAINTY_REASON_TOKENS):
        return True
    status = str(row.get("status") or "").strip().lower()
    if status in DOWNGRADED_STATUSES:
        return True
    return False


def _definitive_claim_present(row: Mapping[str, Any], *, text: str) -> bool:
    explicit = _safe_bool(row.get("definitive_claim_present"))
    if explicit is not None:
        return explicit
    return _contains_any(text, DEFINITIVE_PHRASES)


def _safe_guidance_present(row: Mapping[str, Any], *, text: str) -> bool:
    explicit = _safe_bool(row.get("safe_guidance_present"))
    if explicit is not None:
        return explicit
    return _contains_any(text, SAFE_GUIDANCE_HINTS)


def _fallback_downgraded(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("fallback_downgraded"))
    if explicit is not None:
        return explicit
    status = str(row.get("status") or "").strip().lower()
    if status in DOWNGRADED_STATUSES:
        return True
    next_action = str(row.get("next_action") or "").strip().upper()
    if next_action in DOWNGRADED_ACTIONS:
        return True
    return False


def summarize_policy_uncertainty_safe_fallback_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    policy_uncertain_total = 0
    unsafe_definitive_total = 0
    safe_guidance_missing_total = 0
    fallback_downgrade_missing_total = 0
    uncertainty_safe_ratio_numerator = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        if not _policy_uncertain(row):
            continue

        policy_uncertain_total += 1
        text = _answer_text(row)
        definitive = _definitive_claim_present(row, text=text)
        guidance = _safe_guidance_present(row, text=text)
        downgraded = _fallback_downgraded(row)

        if definitive:
            unsafe_definitive_total += 1
        if not guidance:
            safe_guidance_missing_total += 1
        if not downgraded:
            fallback_downgrade_missing_total += 1
        if (not definitive) and guidance and downgraded:
            uncertainty_safe_ratio_numerator += 1

    uncertainty_safe_ratio = (
        1.0
        if policy_uncertain_total == 0
        else float(uncertainty_safe_ratio_numerator) / float(policy_uncertain_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "policy_uncertain_total": policy_uncertain_total,
        "unsafe_definitive_total": unsafe_definitive_total,
        "safe_guidance_missing_total": safe_guidance_missing_total,
        "fallback_downgrade_missing_total": fallback_downgrade_missing_total,
        "uncertainty_safe_ratio": uncertainty_safe_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_uncertainty_safe_ratio: float,
    max_unsafe_definitive_total: int,
    max_safe_guidance_missing_total: int,
    max_fallback_downgrade_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    uncertainty_safe_ratio = _safe_float(summary.get("uncertainty_safe_ratio"), 0.0)
    unsafe_definitive_total = _safe_int(summary.get("unsafe_definitive_total"), 0)
    safe_guidance_missing_total = _safe_int(summary.get("safe_guidance_missing_total"), 0)
    fallback_downgrade_missing_total = _safe_int(summary.get("fallback_downgrade_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"policy uncertainty window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"policy uncertainty event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if uncertainty_safe_ratio < max(0.0, float(min_uncertainty_safe_ratio)):
        failures.append(
            "policy uncertainty safe ratio below minimum: "
            f"{uncertainty_safe_ratio:.4f} < {float(min_uncertainty_safe_ratio):.4f}"
        )
    if unsafe_definitive_total > max(0, int(max_unsafe_definitive_total)):
        failures.append(
            f"policy uncertainty unsafe-definitive total exceeded: {unsafe_definitive_total} > {int(max_unsafe_definitive_total)}"
        )
    if safe_guidance_missing_total > max(0, int(max_safe_guidance_missing_total)):
        failures.append(
            "policy uncertainty missing-safe-guidance total exceeded: "
            f"{safe_guidance_missing_total} > {int(max_safe_guidance_missing_total)}"
        )
    if fallback_downgrade_missing_total > max(0, int(max_fallback_downgrade_missing_total)):
        failures.append(
            "policy uncertainty missing-fallback-downgrade total exceeded: "
            f"{fallback_downgrade_missing_total} > {int(max_fallback_downgrade_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"policy uncertainty stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Policy Uncertainty Safe Fallback Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- policy_uncertain_total: {_safe_int(summary.get('policy_uncertain_total'), 0)}")
    lines.append(f"- uncertainty_safe_ratio: {_safe_float(summary.get('uncertainty_safe_ratio'), 0.0):.4f}")
    lines.append(f"- unsafe_definitive_total: {_safe_int(summary.get('unsafe_definitive_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate policy uncertainty safe fallback quality.")
    parser.add_argument("--events-jsonl", default="var/grounded_answer/policy_uncertainty_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_policy_uncertainty_safe_fallback_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-uncertainty-safe-ratio", type=float, default=0.0)
    parser.add_argument("--max-unsafe-definitive-total", type=int, default=1000000)
    parser.add_argument("--max-safe-guidance-missing-total", type=int, default=1000000)
    parser.add_argument("--max-fallback-downgrade-missing-total", type=int, default=1000000)
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
    summary = summarize_policy_uncertainty_safe_fallback_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_uncertainty_safe_ratio=max(0.0, float(args.min_uncertainty_safe_ratio)),
        max_unsafe_definitive_total=max(0, int(args.max_unsafe_definitive_total)),
        max_safe_guidance_missing_total=max(0, int(args.max_safe_guidance_missing_total)),
        max_fallback_downgrade_missing_total=max(0, int(args.max_fallback_downgrade_missing_total)),
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
                "min_uncertainty_safe_ratio": float(args.min_uncertainty_safe_ratio),
                "max_unsafe_definitive_total": int(args.max_unsafe_definitive_total),
                "max_safe_guidance_missing_total": int(args.max_safe_guidance_missing_total),
                "max_fallback_downgrade_missing_total": int(args.max_fallback_downgrade_missing_total),
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
    print(f"policy_uncertain_total={_safe_int(summary.get('policy_uncertain_total'), 0)}")
    print(f"uncertainty_safe_ratio={_safe_float(summary.get('uncertainty_safe_ratio'), 0.0):.4f}")
    print(f"unsafe_definitive_total={_safe_int(summary.get('unsafe_definitive_total'), 0)}")
    print(f"safe_guidance_missing_total={_safe_int(summary.get('safe_guidance_missing_total'), 0)}")
    print(
        "fallback_downgrade_missing_total="
        f"{_safe_int(summary.get('fallback_downgrade_missing_total'), 0)}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
