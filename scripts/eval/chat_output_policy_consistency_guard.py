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


def _normalize_decision(value: Any) -> str:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "ALLOWED": "ALLOW",
        "PERMIT": "ALLOW",
        "BLOCK": "DENY",
        "DENIED": "DENY",
        "REJECT": "DENY",
        "ASK_CLARIFICATION": "CLARIFY",
        "NEED_CLARIFY": "CLARIFY",
        "CLARIFICATION": "CLARIFY",
        "FALLBACK": "FALLBACK",
        "ABSTAIN": "FALLBACK",
    }
    return aliases.get(token, token)


def _policy_decision(row: Mapping[str, Any]) -> str:
    return _normalize_decision(row.get("policy_decision") or row.get("policy_result") or row.get("guard_policy_decision"))


def _output_decision(row: Mapping[str, Any]) -> str:
    return _normalize_decision(row.get("output_decision") or row.get("final_action") or row.get("delivery_decision"))


def _has_reason(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("downgrade_reason") or "").strip())


def summarize_output_policy_consistency_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    decision_total = 0
    policy_checked_total = 0
    mismatch_total = 0
    deny_bypass_total = 0
    clarify_ignored_total = 0
    missing_reason_code_total = 0
    downgrade_without_reason_total = 0

    for row in rows:
        decision_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        policy = _policy_decision(row)
        output = _output_decision(row)
        if not policy or not output:
            continue
        policy_checked_total += 1

        downgraded = _safe_bool(row.get("downgraded"), False)
        consistent = True
        if "policy_consistent" in row:
            consistent = _safe_bool(row.get("policy_consistent"), True)
        else:
            if policy == "DENY" and output == "ALLOW":
                consistent = False
                deny_bypass_total += 1
            elif policy == "CLARIFY" and output == "ALLOW" and not _safe_bool(row.get("clarification_prompted"), False):
                consistent = False
                clarify_ignored_total += 1

        if not consistent:
            mismatch_total += 1
            if not _has_reason(row):
                missing_reason_code_total += 1

        if downgraded and not _has_reason(row):
            downgrade_without_reason_total += 1

    consistency_ratio = (
        1.0 if policy_checked_total == 0 else float(policy_checked_total - mismatch_total) / float(policy_checked_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "decision_total": decision_total,
        "policy_checked_total": policy_checked_total,
        "mismatch_total": mismatch_total,
        "consistency_ratio": consistency_ratio,
        "deny_bypass_total": deny_bypass_total,
        "clarify_ignored_total": clarify_ignored_total,
        "missing_reason_code_total": missing_reason_code_total,
        "downgrade_without_reason_total": downgrade_without_reason_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_policy_checked_total: int,
    min_consistency_ratio: float,
    max_mismatch_total: int,
    max_deny_bypass_total: int,
    max_clarify_ignored_total: int,
    max_missing_reason_code_total: int,
    max_downgrade_without_reason_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    policy_checked_total = _safe_int(summary.get("policy_checked_total"), 0)
    consistency_ratio = _safe_float(summary.get("consistency_ratio"), 0.0)
    mismatch_total = _safe_int(summary.get("mismatch_total"), 0)
    deny_bypass_total = _safe_int(summary.get("deny_bypass_total"), 0)
    clarify_ignored_total = _safe_int(summary.get("clarify_ignored_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    downgrade_without_reason_total = _safe_int(summary.get("downgrade_without_reason_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat output policy window too small: {window_size} < {int(min_window)}")
    if policy_checked_total < max(0, int(min_policy_checked_total)):
        failures.append(
            f"chat output policy checked total too small: {policy_checked_total} < {int(min_policy_checked_total)}"
        )
    if window_size == 0:
        return failures

    if consistency_ratio < max(0.0, float(min_consistency_ratio)):
        failures.append(
            f"chat output policy consistency ratio below minimum: {consistency_ratio:.4f} < {float(min_consistency_ratio):.4f}"
        )
    if mismatch_total > max(0, int(max_mismatch_total)):
        failures.append(f"chat output policy mismatch total exceeded: {mismatch_total} > {int(max_mismatch_total)}")
    if deny_bypass_total > max(0, int(max_deny_bypass_total)):
        failures.append(f"chat output policy deny bypass total exceeded: {deny_bypass_total} > {int(max_deny_bypass_total)}")
    if clarify_ignored_total > max(0, int(max_clarify_ignored_total)):
        failures.append(
            f"chat output policy clarify-ignored total exceeded: {clarify_ignored_total} > {int(max_clarify_ignored_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"chat output policy missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if downgrade_without_reason_total > max(0, int(max_downgrade_without_reason_total)):
        failures.append(
            "chat output policy downgrade-without-reason total exceeded: "
            f"{downgrade_without_reason_total} > {int(max_downgrade_without_reason_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat output policy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Output Policy Consistency Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- policy_checked_total: {_safe_int(summary.get('policy_checked_total'), 0)}")
    lines.append(f"- consistency_ratio: {_safe_float(summary.get('consistency_ratio'), 0.0):.4f}")
    lines.append(f"- mismatch_total: {_safe_int(summary.get('mismatch_total'), 0)}")
    lines.append(f"- deny_bypass_total: {_safe_int(summary.get('deny_bypass_total'), 0)}")
    lines.append(f"- clarify_ignored_total: {_safe_int(summary.get('clarify_ignored_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat output policy consistency guard quality.")
    parser.add_argument("--events-jsonl", default="var/chat_output_guard/output_policy_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_output_policy_consistency_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-policy-checked-total", type=int, default=0)
    parser.add_argument("--min-consistency-ratio", type=float, default=0.0)
    parser.add_argument("--max-mismatch-total", type=int, default=0)
    parser.add_argument("--max-deny-bypass-total", type=int, default=0)
    parser.add_argument("--max-clarify-ignored-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-downgrade-without-reason-total", type=int, default=0)
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
    summary = summarize_output_policy_consistency_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_policy_checked_total=max(0, int(args.min_policy_checked_total)),
        min_consistency_ratio=max(0.0, float(args.min_consistency_ratio)),
        max_mismatch_total=max(0, int(args.max_mismatch_total)),
        max_deny_bypass_total=max(0, int(args.max_deny_bypass_total)),
        max_clarify_ignored_total=max(0, int(args.max_clarify_ignored_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_downgrade_without_reason_total=max(0, int(args.max_downgrade_without_reason_total)),
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
                "min_policy_checked_total": int(args.min_policy_checked_total),
                "min_consistency_ratio": float(args.min_consistency_ratio),
                "max_mismatch_total": int(args.max_mismatch_total),
                "max_deny_bypass_total": int(args.max_deny_bypass_total),
                "max_clarify_ignored_total": int(args.max_clarify_ignored_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_downgrade_without_reason_total": int(args.max_downgrade_without_reason_total),
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
    print(f"policy_checked_total={_safe_int(summary.get('policy_checked_total'), 0)}")
    print(f"mismatch_total={_safe_int(summary.get('mismatch_total'), 0)}")
    print(f"deny_bypass_total={_safe_int(summary.get('deny_bypass_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
