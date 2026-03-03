#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


BAND_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
HANDOFF_ACTIONS = {"HANDOFF", "ESCALATE", "APPROVAL_QUEUE", "HUMAN_APPROVAL", "REVIEW_QUEUE"}
MANDATORY_R2_PHRASES = ("추가 확인", "확인이 필요", "검토", "승인 후", "확인 후")
MANDATORY_R3_PHRASES = ("자동으로 처리할 수 없습니다", "상담", "담당자", "승인 필요", "티켓", "문의")
FORBIDDEN_HIGH_RISK_PHRASES = ("처리 완료", "실행했습니다", "완료되었습니다", "확정되었습니다", "cancelled now", "refund completed")
EXECUTION_CLAIM_PHRASES = ("실행했습니다", "처리했습니다", "완료되었습니다", "환불했습니다", "취소했습니다", "executed", "completed")
HANDOFF_HINT_PHRASES = ("상담", "담당자", "티켓", "문의", "승인")


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_band(value: Any) -> str:
    token = _normalize_token(value)
    if token in BAND_ORDER:
        return token
    if token in {"0", "RISK_0"}:
        return "R0"
    if token in {"1", "RISK_1"}:
        return "R1"
    if token in {"2", "RISK_2"}:
        return "R2"
    if token in {"3", "RISK_3"}:
        return "R3"
    return ""


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


def _response_text(row: Mapping[str, Any]) -> str:
    return str(row.get("response_text") or row.get("assistant_message") or row.get("output_text") or "")


def _action(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("approval_action") or row.get("next_action") or row.get("route_result"))


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    hay = text.lower()
    return any(phrase.lower() in hay for phrase in phrases)


def _mandatory_phrase_present(row: Mapping[str, Any], *, band: str, text: str) -> bool:
    explicit = _safe_bool(row.get("mandatory_phrase_present"))
    if explicit is not None:
        return explicit
    if band == "R2":
        return _contains_any(text, MANDATORY_R2_PHRASES)
    if band == "R3":
        return _contains_any(text, MANDATORY_R3_PHRASES)
    return True


def _forbidden_phrase_present(row: Mapping[str, Any], *, text: str) -> bool:
    explicit = _safe_bool(row.get("forbidden_phrase_present"))
    if explicit is not None:
        return explicit
    return _contains_any(text, FORBIDDEN_HIGH_RISK_PHRASES)


def _execution_claim_present(row: Mapping[str, Any], *, text: str) -> bool:
    explicit = _safe_bool(row.get("execution_claim_present"))
    if explicit is not None:
        return explicit
    return _contains_any(text, EXECUTION_CLAIM_PHRASES)


def _handoff_present(row: Mapping[str, Any], *, action: str, text: str) -> bool:
    explicit = _safe_bool(row.get("handoff_offered"))
    if explicit is not None:
        return explicit
    if action in HANDOFF_ACTIONS:
        return True
    return _contains_any(text, HANDOFF_HINT_PHRASES)


def summarize_answer_band_policy_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    missing_band_total = 0
    high_risk_total = 0
    policy_violation_total = 0
    forbidden_phrase_total = 0
    missing_mandatory_phrase_total = 0
    r3_execution_claim_total = 0
    r3_handoff_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        band = _normalize_band(row.get("risk_band") or row.get("assigned_band"))
        if not band:
            missing_band_total += 1
            continue
        if BAND_ORDER[band] < BAND_ORDER["R2"]:
            continue

        high_risk_total += 1
        text = _response_text(row)
        action = _action(row)

        violations_for_event = False
        mandatory_present = _mandatory_phrase_present(row, band=band, text=text)
        if not mandatory_present:
            missing_mandatory_phrase_total += 1
            violations_for_event = True

        forbidden_present = _forbidden_phrase_present(row, text=text)
        if forbidden_present:
            forbidden_phrase_total += 1
            violations_for_event = True

        if band == "R3":
            exec_claim = _execution_claim_present(row, text=text)
            if exec_claim:
                r3_execution_claim_total += 1
                violations_for_event = True
            handoff_ok = _handoff_present(row, action=action, text=text)
            if not handoff_ok:
                r3_handoff_missing_total += 1
                violations_for_event = True

        if violations_for_event:
            policy_violation_total += 1

    safe_policy_coverage_ratio = (
        1.0 if high_risk_total == 0 else float(high_risk_total - policy_violation_total) / float(high_risk_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "missing_band_total": missing_band_total,
        "high_risk_total": high_risk_total,
        "policy_violation_total": policy_violation_total,
        "safe_policy_coverage_ratio": safe_policy_coverage_ratio,
        "forbidden_phrase_total": forbidden_phrase_total,
        "missing_mandatory_phrase_total": missing_mandatory_phrase_total,
        "r3_execution_claim_total": r3_execution_claim_total,
        "r3_handoff_missing_total": r3_handoff_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_safe_policy_coverage_ratio: float,
    max_missing_band_total: int,
    max_policy_violation_total: int,
    max_forbidden_phrase_total: int,
    max_missing_mandatory_phrase_total: int,
    max_r3_execution_claim_total: int,
    max_r3_handoff_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    safe_policy_coverage_ratio = _safe_float(summary.get("safe_policy_coverage_ratio"), 0.0)
    missing_band_total = _safe_int(summary.get("missing_band_total"), 0)
    policy_violation_total = _safe_int(summary.get("policy_violation_total"), 0)
    forbidden_phrase_total = _safe_int(summary.get("forbidden_phrase_total"), 0)
    missing_mandatory_phrase_total = _safe_int(summary.get("missing_mandatory_phrase_total"), 0)
    r3_execution_claim_total = _safe_int(summary.get("r3_execution_claim_total"), 0)
    r3_handoff_missing_total = _safe_int(summary.get("r3_handoff_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"answer band policy window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"answer band policy event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if safe_policy_coverage_ratio < max(0.0, float(min_safe_policy_coverage_ratio)):
        failures.append(
            f"answer band policy safe coverage ratio below minimum: {safe_policy_coverage_ratio:.4f} < {float(min_safe_policy_coverage_ratio):.4f}"
        )
    if missing_band_total > max(0, int(max_missing_band_total)):
        failures.append(f"answer band policy missing-band total exceeded: {missing_band_total} > {int(max_missing_band_total)}")
    if policy_violation_total > max(0, int(max_policy_violation_total)):
        failures.append(
            f"answer band policy violation total exceeded: {policy_violation_total} > {int(max_policy_violation_total)}"
        )
    if forbidden_phrase_total > max(0, int(max_forbidden_phrase_total)):
        failures.append(
            f"answer band policy forbidden-phrase total exceeded: {forbidden_phrase_total} > {int(max_forbidden_phrase_total)}"
        )
    if missing_mandatory_phrase_total > max(0, int(max_missing_mandatory_phrase_total)):
        failures.append(
            "answer band policy missing-mandatory-phrase total exceeded: "
            f"{missing_mandatory_phrase_total} > {int(max_missing_mandatory_phrase_total)}"
        )
    if r3_execution_claim_total > max(0, int(max_r3_execution_claim_total)):
        failures.append(
            f"answer band policy R3 execution-claim total exceeded: {r3_execution_claim_total} > {int(max_r3_execution_claim_total)}"
        )
    if r3_handoff_missing_total > max(0, int(max_r3_handoff_missing_total)):
        failures.append(
            f"answer band policy R3 handoff-missing total exceeded: {r3_handoff_missing_total} > {int(max_r3_handoff_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"answer band policy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Answer Band Policy Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- safe_policy_coverage_ratio: {_safe_float(summary.get('safe_policy_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- policy_violation_total: {_safe_int(summary.get('policy_violation_total'), 0)}")
    lines.append(f"- r3_execution_claim_total: {_safe_int(summary.get('r3_execution_claim_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate answer policy enforcement by risk band.")
    parser.add_argument("--events-jsonl", default="var/risk_banding/band_policy_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_answer_band_policy_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-safe-policy-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-band-total", type=int, default=1000000)
    parser.add_argument("--max-policy-violation-total", type=int, default=1000000)
    parser.add_argument("--max-forbidden-phrase-total", type=int, default=1000000)
    parser.add_argument("--max-missing-mandatory-phrase-total", type=int, default=1000000)
    parser.add_argument("--max-r3-execution-claim-total", type=int, default=1000000)
    parser.add_argument("--max-r3-handoff-missing-total", type=int, default=1000000)
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
    summary = summarize_answer_band_policy_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_safe_policy_coverage_ratio=max(0.0, float(args.min_safe_policy_coverage_ratio)),
        max_missing_band_total=max(0, int(args.max_missing_band_total)),
        max_policy_violation_total=max(0, int(args.max_policy_violation_total)),
        max_forbidden_phrase_total=max(0, int(args.max_forbidden_phrase_total)),
        max_missing_mandatory_phrase_total=max(0, int(args.max_missing_mandatory_phrase_total)),
        max_r3_execution_claim_total=max(0, int(args.max_r3_execution_claim_total)),
        max_r3_handoff_missing_total=max(0, int(args.max_r3_handoff_missing_total)),
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
                "min_safe_policy_coverage_ratio": float(args.min_safe_policy_coverage_ratio),
                "max_missing_band_total": int(args.max_missing_band_total),
                "max_policy_violation_total": int(args.max_policy_violation_total),
                "max_forbidden_phrase_total": int(args.max_forbidden_phrase_total),
                "max_missing_mandatory_phrase_total": int(args.max_missing_mandatory_phrase_total),
                "max_r3_execution_claim_total": int(args.max_r3_execution_claim_total),
                "max_r3_handoff_missing_total": int(args.max_r3_handoff_missing_total),
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
    print(f"safe_policy_coverage_ratio={_safe_float(summary.get('safe_policy_coverage_ratio'), 0.0):.4f}")
    print(f"policy_violation_total={_safe_int(summary.get('policy_violation_total'), 0)}")
    print(f"r3_execution_claim_total={_safe_int(summary.get('r3_execution_claim_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
