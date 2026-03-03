#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ALLOWED_ACTIONS = {
    "ALLOW",
    "DENY",
    "ASK_CLARIFICATION",
    "REQUIRE_CONFIRMATION",
    "HANDOFF",
}
ACTION_ALIASES = {
    "BLOCK": "DENY",
    "ESCALATE": "HANDOFF",
    "HUMAN_HANDOFF": "HANDOFF",
    "CONFIRM": "REQUIRE_CONFIRMATION",
    "CLARIFY": "ASK_CLARIFICATION",
}


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


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return "UNKNOWN"
    return ACTION_ALIASES.get(text, text)


def _event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "policy_eval": "POLICY_EVAL",
        "policy_evaluated": "POLICY_EVAL",
        "eval": "POLICY_EVAL",
        "policy_conflict": "POLICY_CONFLICT",
        "conflict": "POLICY_CONFLICT",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _as_rule_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


def _decision_key(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("eval_key") or row.get("decision_fingerprint") or "").strip()
    if explicit:
        return explicit
    intent = str(row.get("intent") or "").strip().upper()
    user_tier = str(row.get("user_tier") or "").strip().upper()
    risk_level = str(row.get("risk_level") or "").strip().upper()
    reliability = str(row.get("reliability_level") or "").strip().upper()
    locale = str(row.get("locale") or "").strip()
    candidate = "|".join([intent, user_tier, risk_level, reliability, locale]).strip("|")
    return candidate


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


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
        if isinstance(payload, Mapping):
            rows.append({str(k): v for k, v in payload.items()})
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


def summarize_policy_eval_trace(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    eval_total = 0
    missing_request_id_total = 0
    missing_policy_version_total = 0
    missing_matched_rule_total = 0
    unknown_final_action_total = 0
    conflict_total = 0
    conflict_unresolved_total = 0
    latencies: list[float] = []
    decision_actions_by_key: dict[str, set[str]] = {}

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event not in {"POLICY_EVAL", "POLICY_CONFLICT"}:
            continue
        eval_total += 1

        request_id = str(row.get("request_id") or row.get("trace_id") or "").strip()
        if not request_id:
            missing_request_id_total += 1

        policy_version = str(row.get("policy_version") or row.get("bundle_version") or "").strip()
        if not policy_version:
            missing_policy_version_total += 1

        matched_rule_ids = _as_rule_ids(row.get("matched_rule_ids") or row.get("matched_rules"))
        if not matched_rule_ids:
            missing_matched_rule_total += 1

        final_action = _normalize_action(row.get("final_action") or row.get("decision") or row.get("action"))
        if final_action not in ALLOWED_ACTIONS:
            unknown_final_action_total += 1

        key = _decision_key(row)
        if key:
            decision_actions_by_key.setdefault(key, set()).add(final_action)

        latency_ms = _safe_float(row.get("latency_ms"), -1.0)
        if latency_ms >= 0.0:
            latencies.append(latency_ms)

        has_conflict = event == "POLICY_CONFLICT" or _safe_bool(row.get("conflict_detected"), False)
        if has_conflict:
            conflict_total += 1
            resolved_by = str(row.get("resolved_by") or row.get("resolution") or "").strip()
            winner_rule = str(row.get("winner_rule_id") or "").strip()
            if not resolved_by and not winner_rule:
                conflict_unresolved_total += 1

    non_deterministic_key_total = sum(1 for actions in decision_actions_by_key.values() if len(actions) > 1)
    latency_p95_ms = _p95(latencies)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "eval_total": eval_total,
        "missing_request_id_total": missing_request_id_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_matched_rule_total": missing_matched_rule_total,
        "unknown_final_action_total": unknown_final_action_total,
        "non_deterministic_key_total": non_deterministic_key_total,
        "conflict_total": conflict_total,
        "conflict_unresolved_total": conflict_unresolved_total,
        "latency_p95_ms": latency_p95_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_request_id_total: int,
    max_missing_policy_version_total: int,
    max_missing_matched_rule_total: int,
    max_unknown_final_action_total: int,
    max_non_deterministic_key_total: int,
    max_conflict_unresolved_total: int,
    max_latency_p95_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_request_id_total = _safe_int(summary.get("missing_request_id_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_matched_rule_total = _safe_int(summary.get("missing_matched_rule_total"), 0)
    unknown_final_action_total = _safe_int(summary.get("unknown_final_action_total"), 0)
    non_deterministic_key_total = _safe_int(summary.get("non_deterministic_key_total"), 0)
    conflict_unresolved_total = _safe_int(summary.get("conflict_unresolved_total"), 0)
    latency_p95_ms = _safe_float(summary.get("latency_p95_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"policy eval window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_request_id_total > max(0, int(max_missing_request_id_total)):
        failures.append(
            f"policy eval missing request id total exceeded: {missing_request_id_total} > {int(max_missing_request_id_total)}"
        )
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "policy eval missing policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_matched_rule_total > max(0, int(max_missing_matched_rule_total)):
        failures.append(
            f"policy eval missing matched rule total exceeded: {missing_matched_rule_total} > {int(max_missing_matched_rule_total)}"
        )
    if unknown_final_action_total > max(0, int(max_unknown_final_action_total)):
        failures.append(
            f"policy eval unknown final action total exceeded: {unknown_final_action_total} > {int(max_unknown_final_action_total)}"
        )
    if non_deterministic_key_total > max(0, int(max_non_deterministic_key_total)):
        failures.append(
            "policy eval non-deterministic key total exceeded: "
            f"{non_deterministic_key_total} > {int(max_non_deterministic_key_total)}"
        )
    if conflict_unresolved_total > max(0, int(max_conflict_unresolved_total)):
        failures.append(
            "policy eval unresolved conflict total exceeded: "
            f"{conflict_unresolved_total} > {int(max_conflict_unresolved_total)}"
        )
    if latency_p95_ms > max(0.0, float(max_latency_p95_ms)):
        failures.append(f"policy eval latency p95 too high: {latency_p95_ms:.1f}ms > {float(max_latency_p95_ms):.1f}ms")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"policy eval events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Policy Eval Trace")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- eval_total: {_safe_int(summary.get('eval_total'), 0)}")
    lines.append(f"- non_deterministic_key_total: {_safe_int(summary.get('non_deterministic_key_total'), 0)}")
    lines.append(f"- conflict_unresolved_total: {_safe_int(summary.get('conflict_unresolved_total'), 0)}")
    lines.append(f"- latency_p95_ms: {_safe_float(summary.get('latency_p95_ms'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat policy runtime trace determinism and conflict handling.")
    parser.add_argument("--events-jsonl", default="var/chat_policy/policy_eval_audit.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_policy_eval_trace")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-request-id-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-matched-rule-total", type=int, default=0)
    parser.add_argument("--max-unknown-final-action-total", type=int, default=0)
    parser.add_argument("--max-non-deterministic-key-total", type=int, default=0)
    parser.add_argument("--max-conflict-unresolved-total", type=int, default=0)
    parser.add_argument("--max-latency-p95-ms", type=float, default=2000.0)
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
    summary = summarize_policy_eval_trace(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_request_id_total=max(0, int(args.max_missing_request_id_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_matched_rule_total=max(0, int(args.max_missing_matched_rule_total)),
        max_unknown_final_action_total=max(0, int(args.max_unknown_final_action_total)),
        max_non_deterministic_key_total=max(0, int(args.max_non_deterministic_key_total)),
        max_conflict_unresolved_total=max(0, int(args.max_conflict_unresolved_total)),
        max_latency_p95_ms=max(0.0, float(args.max_latency_p95_ms)),
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
                "max_missing_request_id_total": int(args.max_missing_request_id_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_matched_rule_total": int(args.max_missing_matched_rule_total),
                "max_unknown_final_action_total": int(args.max_unknown_final_action_total),
                "max_non_deterministic_key_total": int(args.max_non_deterministic_key_total),
                "max_conflict_unresolved_total": int(args.max_conflict_unresolved_total),
                "max_latency_p95_ms": float(args.max_latency_p95_ms),
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
    print(f"eval_total={_safe_int(summary.get('eval_total'), 0)}")
    print(f"non_deterministic_key_total={_safe_int(summary.get('non_deterministic_key_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
