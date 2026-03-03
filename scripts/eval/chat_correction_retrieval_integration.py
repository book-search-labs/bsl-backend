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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "resolved_at", "generated_at"):
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


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]
    return []


def _correction_candidate_total(row: Mapping[str, Any]) -> int:
    explicit = _safe_int(row.get("correction_candidate_total"), -1)
    if explicit >= 0:
        return explicit
    ids = _as_list(row.get("matched_correction_ids") or row.get("candidate_correction_ids"))
    return len(ids)


def _correction_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("correction_applied"), False) or _safe_bool(row.get("correction_hit"), False):
        return True
    if str(row.get("matched_correction_id") or "").strip():
        return True
    return len(_as_list(row.get("applied_correction_ids"))) > 0


def _policy_conflict(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("policy_conflict"), False) or _safe_bool(row.get("correction_conflict_with_policy"), False):
        return True
    status = str(row.get("resolution_status") or "").strip().upper()
    return status in {"CONFLICT", "CONFLICTED"}


def _conflict_handled(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("safe_fallback_used"), False) or _safe_bool(row.get("fallback_used"), False):
        return True
    strategy = str(row.get("conflict_strategy") or row.get("resolution_strategy") or "").strip().upper()
    return strategy in {"SAFE_FALLBACK", "ASK", "ABSTAIN", "ESCALATE", "HUMAN_HANDOFF"}


def _retrieval_latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("retrieval_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("retrieval_latency_seconds")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_correction_retrieval_integration(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    request_total = 0
    correction_hit_total = 0
    override_total = 0
    stale_hit_total = 0
    precedence_violation_total = 0
    policy_conflict_total = 0
    policy_conflict_unhandled_total = 0
    missing_reason_code_total = 0
    latency_samples: list[float] = []

    for row in rows:
        request_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        candidate_total = _correction_candidate_total(row)
        applied = _correction_applied(row)
        route = str(row.get("retrieval_route") or row.get("retrieval_order") or "").strip().upper()

        if applied:
            correction_hit_total += 1
            if _safe_bool(row.get("correction_override"), False):
                override_total += 1
            if _safe_bool(row.get("correction_stale"), False) or _safe_bool(row.get("expired_correction_used"), False):
                stale_hit_total += 1
            if not str(row.get("reason_code") or "").strip():
                missing_reason_code_total += 1
        elif candidate_total > 0 and route in {"RAG_FIRST", "SEARCH_FIRST", "KNOWLEDGE_FIRST"}:
            precedence_violation_total += 1

        conflict = _policy_conflict(row)
        if conflict:
            policy_conflict_total += 1
            if not _conflict_handled(row):
                policy_conflict_unhandled_total += 1

        latency_samples.append(_retrieval_latency_ms(row))

    hit_ratio = 1.0 if request_total == 0 else float(correction_hit_total) / float(request_total)
    p95_retrieval_latency_ms = _p95(latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "request_total": request_total,
        "correction_hit_total": correction_hit_total,
        "hit_ratio": hit_ratio,
        "override_total": override_total,
        "stale_hit_total": stale_hit_total,
        "precedence_violation_total": precedence_violation_total,
        "policy_conflict_total": policy_conflict_total,
        "policy_conflict_unhandled_total": policy_conflict_unhandled_total,
        "missing_reason_code_total": missing_reason_code_total,
        "p95_retrieval_latency_ms": p95_retrieval_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_request_total: int,
    min_hit_ratio: float,
    max_stale_hit_total: int,
    max_precedence_violation_total: int,
    max_policy_conflict_unhandled_total: int,
    max_missing_reason_code_total: int,
    max_p95_retrieval_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    request_total = _safe_int(summary.get("request_total"), 0)
    hit_ratio = _safe_float(summary.get("hit_ratio"), 0.0)
    stale_hit_total = _safe_int(summary.get("stale_hit_total"), 0)
    precedence_violation_total = _safe_int(summary.get("precedence_violation_total"), 0)
    policy_conflict_unhandled_total = _safe_int(summary.get("policy_conflict_unhandled_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    p95_retrieval_latency_ms = _safe_float(summary.get("p95_retrieval_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat correction retrieval window too small: {window_size} < {int(min_window)}")
    if request_total < max(0, int(min_request_total)):
        failures.append(f"chat correction retrieval request total too small: {request_total} < {int(min_request_total)}")
    if window_size == 0:
        return failures

    if hit_ratio < max(0.0, float(min_hit_ratio)):
        failures.append(f"chat correction retrieval hit ratio below minimum: {hit_ratio:.4f} < {float(min_hit_ratio):.4f}")
    if stale_hit_total > max(0, int(max_stale_hit_total)):
        failures.append(f"chat correction retrieval stale hit total exceeded: {stale_hit_total} > {int(max_stale_hit_total)}")
    if precedence_violation_total > max(0, int(max_precedence_violation_total)):
        failures.append(
            "chat correction retrieval precedence violation total exceeded: "
            f"{precedence_violation_total} > {int(max_precedence_violation_total)}"
        )
    if policy_conflict_unhandled_total > max(0, int(max_policy_conflict_unhandled_total)):
        failures.append(
            "chat correction retrieval policy conflict unhandled total exceeded: "
            f"{policy_conflict_unhandled_total} > {int(max_policy_conflict_unhandled_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"chat correction retrieval missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if p95_retrieval_latency_ms > max(0.0, float(max_p95_retrieval_latency_ms)):
        failures.append(
            f"chat correction retrieval p95 latency exceeded: {p95_retrieval_latency_ms:.2f}ms > {float(max_p95_retrieval_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat correction retrieval stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Correction Retrieval Integration")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- request_total: {_safe_int(summary.get('request_total'), 0)}")
    lines.append(f"- correction_hit_total: {_safe_int(summary.get('correction_hit_total'), 0)}")
    lines.append(f"- precedence_violation_total: {_safe_int(summary.get('precedence_violation_total'), 0)}")
    lines.append(f"- policy_conflict_unhandled_total: {_safe_int(summary.get('policy_conflict_unhandled_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate correction memory retrieval integration quality.")
    parser.add_argument("--events-jsonl", default="var/chat_correction/correction_retrieval_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_correction_retrieval_integration")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-request-total", type=int, default=0)
    parser.add_argument("--min-hit-ratio", type=float, default=0.0)
    parser.add_argument("--max-stale-hit-total", type=int, default=0)
    parser.add_argument("--max-precedence-violation-total", type=int, default=0)
    parser.add_argument("--max-policy-conflict-unhandled-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-p95-retrieval-latency-ms", type=float, default=1000000.0)
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
    summary = summarize_correction_retrieval_integration(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_request_total=max(0, int(args.min_request_total)),
        min_hit_ratio=max(0.0, float(args.min_hit_ratio)),
        max_stale_hit_total=max(0, int(args.max_stale_hit_total)),
        max_precedence_violation_total=max(0, int(args.max_precedence_violation_total)),
        max_policy_conflict_unhandled_total=max(0, int(args.max_policy_conflict_unhandled_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_p95_retrieval_latency_ms=max(0.0, float(args.max_p95_retrieval_latency_ms)),
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
                "min_request_total": int(args.min_request_total),
                "min_hit_ratio": float(args.min_hit_ratio),
                "max_stale_hit_total": int(args.max_stale_hit_total),
                "max_precedence_violation_total": int(args.max_precedence_violation_total),
                "max_policy_conflict_unhandled_total": int(args.max_policy_conflict_unhandled_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_p95_retrieval_latency_ms": float(args.max_p95_retrieval_latency_ms),
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
    print(f"request_total={_safe_int(summary.get('request_total'), 0)}")
    print(f"correction_hit_total={_safe_int(summary.get('correction_hit_total'), 0)}")
    print(f"precedence_violation_total={_safe_int(summary.get('precedence_violation_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
