#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_STRATEGIES = {
    "OFFICIAL_LATEST",
    "TRUST_WEIGHT",
    "SAFE_ABSTAIN",
    "MANUAL_REVIEW",
    "TIE_BREAK_LATEST",
}
SAFE_DECISIONS = {"ABSTAIN", "ESCALATE", "HUMAN_HANDOFF", "DEFER"}
UNSAFE_DECISIONS = {"ANSWER", "EXECUTE", "PROCEED"}


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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _normalize_severity(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"L": "LOW", "M": "MEDIUM", "H": "HIGH"}
    if text in VALID_SEVERITIES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_strategy(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "OFFICIAL": "OFFICIAL_LATEST",
        "LATEST_OFFICIAL": "OFFICIAL_LATEST",
        "ABSTAIN": "SAFE_ABSTAIN",
        "HUMAN_REVIEW": "MANUAL_REVIEW",
    }
    return aliases.get(text, text or "UNKNOWN")


def _normalize_decision(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"BLOCK": "ABSTAIN", "HANDOFF": "HUMAN_HANDOFF"}
    return aliases.get(text, text or "UNKNOWN")


def _is_conflict(row: Mapping[str, Any], severity: str) -> bool:
    if _safe_bool(row.get("is_conflict"), False):
        return True
    return severity in VALID_SEVERITIES


def summarize_resolution_policy(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    conflict_total = 0
    high_conflict_total = 0
    high_conflict_safe_total = 0
    high_conflict_unsafe_total = 0
    official_available_total = 0
    official_preferred_total = 0
    resolved_total = 0
    invalid_strategy_total = 0
    missing_policy_version_total = 0
    missing_reason_code_total = 0

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        severity = _normalize_severity(row.get("conflict_severity") or row.get("severity"))
        strategy = _normalize_strategy(row.get("resolution_strategy") or row.get("strategy"))
        decision = _normalize_decision(row.get("decision") or row.get("action"))

        if strategy not in VALID_STRATEGIES:
            invalid_strategy_total += 1
        if not str(row.get("policy_version") or row.get("resolution_policy_version") or "").strip():
            missing_policy_version_total += 1
        if not str(row.get("reason_code") or row.get("resolution_reason_code") or "").strip():
            missing_reason_code_total += 1

        if not _is_conflict(row, severity):
            continue
        conflict_total += 1

        official_available = _safe_bool(row.get("official_source_available"), False)
        official_selected = _safe_bool(row.get("official_source_selected"), False)
        if official_available:
            official_available_total += 1
            if official_selected or strategy == "OFFICIAL_LATEST":
                official_preferred_total += 1

        resolved = _safe_bool(row.get("resolved"), False) or str(row.get("status") or "").strip().upper() in {
            "RESOLVED",
            "CLOSED",
            "DONE",
        }
        if resolved:
            resolved_total += 1

        if severity == "HIGH":
            high_conflict_total += 1
            if decision in SAFE_DECISIONS:
                high_conflict_safe_total += 1
            if decision in UNSAFE_DECISIONS:
                high_conflict_unsafe_total += 1

    official_preference_ratio = (
        1.0 if official_available_total == 0 else float(official_preferred_total) / float(official_available_total)
    )
    resolution_rate = 1.0 if conflict_total == 0 else float(resolved_total) / float(conflict_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "conflict_total": conflict_total,
        "high_conflict_total": high_conflict_total,
        "high_conflict_safe_total": high_conflict_safe_total,
        "high_conflict_unsafe_total": high_conflict_unsafe_total,
        "official_available_total": official_available_total,
        "official_preferred_total": official_preferred_total,
        "official_preference_ratio": official_preference_ratio,
        "resolved_total": resolved_total,
        "resolution_rate": resolution_rate,
        "invalid_strategy_total": invalid_strategy_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_reason_code_total": missing_reason_code_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_conflict_total: int,
    max_high_conflict_unsafe_total: int,
    min_official_preference_ratio: float,
    min_resolution_rate: float,
    max_invalid_strategy_total: int,
    max_missing_policy_version_total: int,
    max_missing_reason_code_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    conflict_total = _safe_int(summary.get("conflict_total"), 0)
    high_conflict_unsafe_total = _safe_int(summary.get("high_conflict_unsafe_total"), 0)
    official_preference_ratio = _safe_float(summary.get("official_preference_ratio"), 1.0)
    resolution_rate = _safe_float(summary.get("resolution_rate"), 1.0)
    invalid_strategy_total = _safe_int(summary.get("invalid_strategy_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"source conflict resolution window too small: {window_size} < {int(min_window)}")
    if conflict_total < max(0, int(min_conflict_total)):
        failures.append(f"source conflict total too small: {conflict_total} < {int(min_conflict_total)}")
    if window_size == 0:
        return failures

    if high_conflict_unsafe_total > max(0, int(max_high_conflict_unsafe_total)):
        failures.append(
            "source conflict high-severity unsafe decision total exceeded: "
            f"{high_conflict_unsafe_total} > {int(max_high_conflict_unsafe_total)}"
        )
    if official_preference_ratio < max(0.0, float(min_official_preference_ratio)):
        failures.append(
            "source conflict official preference ratio below threshold: "
            f"{official_preference_ratio:.4f} < {float(min_official_preference_ratio):.4f}"
        )
    if resolution_rate < max(0.0, float(min_resolution_rate)):
        failures.append(f"source conflict resolution rate below threshold: {resolution_rate:.4f} < {float(min_resolution_rate):.4f}")
    if invalid_strategy_total > max(0, int(max_invalid_strategy_total)):
        failures.append(f"source conflict invalid strategy total exceeded: {invalid_strategy_total} > {int(max_invalid_strategy_total)}")
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "source conflict missing policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"source conflict missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"source conflict resolution stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_conflict_total_drop: int,
    max_high_conflict_total_drop: int,
    max_high_conflict_unsafe_total_increase: int,
    max_official_preference_ratio_drop: float,
    max_resolution_rate_drop: float,
    max_invalid_strategy_total_increase: int,
    max_missing_policy_version_total_increase: int,
    max_missing_reason_code_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("conflict_total", max_conflict_total_drop),
        ("high_conflict_total", max_high_conflict_total_drop),
    ]
    for key, allowed_drop in baseline_drop_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    baseline_increase_pairs = [
        ("high_conflict_unsafe_total", max_high_conflict_unsafe_total_increase),
        ("invalid_strategy_total", max_invalid_strategy_total_increase),
        ("missing_policy_version_total", max_missing_policy_version_total_increase),
        ("missing_reason_code_total", max_missing_reason_code_total_increase),
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

    baseline_ratio_drop_pairs = [
        ("official_preference_ratio", max_official_preference_ratio_drop),
        ("resolution_rate", max_resolution_rate_drop),
    ]
    for key, allowed_drop in baseline_ratio_drop_pairs:
        base_value = _safe_float(base_summary.get(key), 0.0)
        cur_value = _safe_float(current_summary.get(key), 0.0)
        drop = max(0.0, base_value - cur_value)
        if drop > max(0.0, float(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value:.6f}, current={cur_value:.6f}, "
                f"allowed_drop={float(allowed_drop):.6f}"
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
    lines.append("# Chat Source Conflict Resolution Policy")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- conflict_total: {_safe_int(summary.get('conflict_total'), 0)}")
    lines.append(f"- high_conflict_unsafe_total: {_safe_int(summary.get('high_conflict_unsafe_total'), 0)}")
    lines.append(f"- official_preference_ratio: {_safe_float(summary.get('official_preference_ratio'), 1.0):.4f}")
    lines.append(f"- resolution_rate: {_safe_float(summary.get('resolution_rate'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate source conflict resolution policy behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/source_conflict_resolution_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_source_conflict_resolution_policy")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-conflict-total", type=int, default=0)
    parser.add_argument("--max-high-conflict-unsafe-total", type=int, default=0)
    parser.add_argument("--min-official-preference-ratio", type=float, default=0.0)
    parser.add_argument("--min-resolution-rate", type=float, default=0.0)
    parser.add_argument("--max-invalid-strategy-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-conflict-total-drop", type=int, default=10)
    parser.add_argument("--max-high-conflict-total-drop", type=int, default=5)
    parser.add_argument("--max-high-conflict-unsafe-total-increase", type=int, default=0)
    parser.add_argument("--max-official-preference-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-resolution-rate-drop", type=float, default=0.05)
    parser.add_argument("--max-invalid-strategy-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_resolution_policy(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_conflict_total=max(0, int(args.min_conflict_total)),
        max_high_conflict_unsafe_total=max(0, int(args.max_high_conflict_unsafe_total)),
        min_official_preference_ratio=max(0.0, float(args.min_official_preference_ratio)),
        min_resolution_rate=max(0.0, float(args.min_resolution_rate)),
        max_invalid_strategy_total=max(0, int(args.max_invalid_strategy_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_conflict_total_drop=max(0, int(args.max_conflict_total_drop)),
            max_high_conflict_total_drop=max(0, int(args.max_high_conflict_total_drop)),
            max_high_conflict_unsafe_total_increase=max(0, int(args.max_high_conflict_unsafe_total_increase)),
            max_official_preference_ratio_drop=max(0.0, float(args.max_official_preference_ratio_drop)),
            max_resolution_rate_drop=max(0.0, float(args.max_resolution_rate_drop)),
            max_invalid_strategy_total_increase=max(0, int(args.max_invalid_strategy_total_increase)),
            max_missing_policy_version_total_increase=max(0, int(args.max_missing_policy_version_total_increase)),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "source": {
            "events_jsonl": str(args.events_jsonl),
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
                "min_conflict_total": int(args.min_conflict_total),
                "max_high_conflict_unsafe_total": int(args.max_high_conflict_unsafe_total),
                "min_official_preference_ratio": float(args.min_official_preference_ratio),
                "min_resolution_rate": float(args.min_resolution_rate),
                "max_invalid_strategy_total": int(args.max_invalid_strategy_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_conflict_total_drop": int(args.max_conflict_total_drop),
                "max_high_conflict_total_drop": int(args.max_high_conflict_total_drop),
                "max_high_conflict_unsafe_total_increase": int(args.max_high_conflict_unsafe_total_increase),
                "max_official_preference_ratio_drop": float(args.max_official_preference_ratio_drop),
                "max_resolution_rate_drop": float(args.max_resolution_rate_drop),
                "max_invalid_strategy_total_increase": int(args.max_invalid_strategy_total_increase),
                "max_missing_policy_version_total_increase": int(args.max_missing_policy_version_total_increase),
                "max_missing_reason_code_total_increase": int(args.max_missing_reason_code_total_increase),
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
    print(f"conflict_total={_safe_int(summary.get('conflict_total'), 0)}")
    print(f"high_conflict_unsafe_total={_safe_int(summary.get('high_conflict_unsafe_total'), 0)}")
    print(f"official_preference_ratio={_safe_float(summary.get('official_preference_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
