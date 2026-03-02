#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _intent(row: Mapping[str, Any]) -> str:
    text = str(row.get("intent") or "UNKNOWN").strip().upper()
    return text if text else "UNKNOWN"


def read_events(path: Path, *, window_days: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
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

    threshold = (now or datetime.now(timezone.utc)) - timedelta(days=max(1, int(window_days)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def summarize_unit_economics(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    resolved_total = 0
    unresolved_total = 0
    total_cost_usd = 0.0
    resolved_cost_usd = 0.0
    unresolved_cost_usd = 0.0
    tool_cost_usd = 0.0
    token_cost_usd = 0.0
    latest_ts: datetime | None = None

    by_intent: dict[str, dict[str, float]] = {}

    for row in events:
        intent = _intent(row)
        resolved = _safe_bool(row.get("resolved"), False)
        total_cost = max(0.0, _safe_float(row.get("session_cost_usd"), _safe_float(row.get("cost_usd"), 0.0)))
        tool_cost = max(0.0, _safe_float(row.get("tool_cost_usd"), 0.0))
        token_cost = max(0.0, _safe_float(row.get("token_cost_usd"), 0.0))
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        total_cost_usd += total_cost
        tool_cost_usd += tool_cost
        token_cost_usd += token_cost

        row_intent = by_intent.setdefault(
            intent,
            {
                "resolved_total": 0.0,
                "unresolved_total": 0.0,
                "resolved_cost_usd": 0.0,
                "unresolved_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "tool_cost_usd": 0.0,
                "token_cost_usd": 0.0,
            },
        )
        row_intent["total_cost_usd"] += total_cost
        row_intent["tool_cost_usd"] += tool_cost
        row_intent["token_cost_usd"] += token_cost

        if resolved:
            resolved_total += 1
            resolved_cost_usd += total_cost
            row_intent["resolved_total"] += 1
            row_intent["resolved_cost_usd"] += total_cost
        else:
            unresolved_total += 1
            unresolved_cost_usd += total_cost
            row_intent["unresolved_total"] += 1
            row_intent["unresolved_cost_usd"] += total_cost

    window_size = len(events)
    resolution_rate = 0.0 if window_size == 0 else float(resolved_total) / float(window_size)
    cost_per_resolved_session = 0.0 if resolved_total == 0 else resolved_cost_usd / float(resolved_total)
    unresolved_cost_burn_total = unresolved_cost_usd
    tool_cost_mix_ratio = 0.0 if total_cost_usd <= 0 else tool_cost_usd / total_cost_usd
    token_cost_mix_ratio = 0.0 if total_cost_usd <= 0 else token_cost_usd / total_cost_usd

    intent_rows = []
    for intent, row in sorted(by_intent.items(), key=lambda item: (-item[1]["total_cost_usd"], item[0])):
        resolved_cnt = int(row["resolved_total"])
        unresolved_cnt = int(row["unresolved_total"])
        resolved_cost = float(row["resolved_cost_usd"])
        unresolved_cost = float(row["unresolved_cost_usd"])
        total_intent_cost = float(row["total_cost_usd"])
        intent_tool_cost = float(row["tool_cost_usd"])
        intent_token_cost = float(row["token_cost_usd"])
        intent_rows.append(
            {
                "intent": intent,
                "resolved_total": resolved_cnt,
                "unresolved_total": unresolved_cnt,
                "resolution_rate": 0.0
                if resolved_cnt + unresolved_cnt == 0
                else float(resolved_cnt) / float(resolved_cnt + unresolved_cnt),
                "cost_per_resolved_session": 0.0 if resolved_cnt == 0 else resolved_cost / float(resolved_cnt),
                "unresolved_cost_burn_total": unresolved_cost,
                "tool_cost_mix_ratio": 0.0 if total_intent_cost <= 0 else intent_tool_cost / total_intent_cost,
                "token_cost_mix_ratio": 0.0 if total_intent_cost <= 0 else intent_token_cost / total_intent_cost,
            }
        )

    stale_days = 0.0
    if latest_ts is not None:
        stale_days = max(0.0, (now_dt - latest_ts).total_seconds() / 86400.0)

    return {
        "window_size": window_size,
        "resolved_total": resolved_total,
        "unresolved_total": unresolved_total,
        "resolution_rate": resolution_rate,
        "cost_per_resolved_session": cost_per_resolved_session,
        "unresolved_cost_burn_total": unresolved_cost_burn_total,
        "tool_cost_mix_ratio": tool_cost_mix_ratio,
        "token_cost_mix_ratio": token_cost_mix_ratio,
        "total_cost_usd": total_cost_usd,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_days": stale_days,
        "intents": intent_rows,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_resolution_rate: float,
    max_cost_per_resolved_session: float,
    max_unresolved_cost_burn_total: float,
    max_tool_cost_mix_ratio: float,
    max_stale_days: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    resolution_rate = _safe_float(summary.get("resolution_rate"), 0.0)
    cost_per_resolved = _safe_float(summary.get("cost_per_resolved_session"), 0.0)
    unresolved_burn = _safe_float(summary.get("unresolved_cost_burn_total"), 0.0)
    tool_mix = _safe_float(summary.get("tool_cost_mix_ratio"), 0.0)
    stale_days = _safe_float(summary.get("stale_days"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"unit economics window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures
    if resolution_rate < max(0.0, float(min_resolution_rate)):
        failures.append(f"resolution rate below threshold: {resolution_rate:.4f} < {float(min_resolution_rate):.4f}")
    if cost_per_resolved > max(0.0, float(max_cost_per_resolved_session)):
        failures.append(
            f"cost per resolved session exceeded: {cost_per_resolved:.4f} > {float(max_cost_per_resolved_session):.4f}"
        )
    if unresolved_burn > max(0.0, float(max_unresolved_cost_burn_total)):
        failures.append(
            f"unresolved cost burn exceeded: {unresolved_burn:.4f} > {float(max_unresolved_cost_burn_total):.4f}"
        )
    if tool_mix > max(0.0, float(max_tool_cost_mix_ratio)):
        failures.append(f"tool cost mix exceeded: {tool_mix:.4f} > {float(max_tool_cost_mix_ratio):.4f}")
    if stale_days > max(0.0, float(max_stale_days)):
        failures.append(f"unit economics events stale: {stale_days:.2f}d > {float(max_stale_days):.2f}d")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Unit Economics SLO")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- resolution_rate: {_safe_float(summary.get('resolution_rate'), 0.0):.4f}")
    lines.append(f"- cost_per_resolved_session: {_safe_float(summary.get('cost_per_resolved_session'), 0.0):.4f}")
    lines.append(f"- unresolved_cost_burn_total: {_safe_float(summary.get('unresolved_cost_burn_total'), 0.0):.4f}")
    lines.append(f"- tool_cost_mix_ratio: {_safe_float(summary.get('tool_cost_mix_ratio'), 0.0):.4f}")
    lines.append(f"- token_cost_mix_ratio: {_safe_float(summary.get('token_cost_mix_ratio'), 0.0):.4f}")

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
    parser = argparse.ArgumentParser(description="Evaluate chat unit economics SLO from resolved/unresolved session cost events.")
    parser.add_argument("--events-jsonl", default="var/chat_finops/session_cost_events.jsonl")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_unit_economics_slo")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-resolution-rate", type=float, default=0.80)
    parser.add_argument("--max-cost-per-resolved-session", type=float, default=2.0)
    parser.add_argument("--max-unresolved-cost-burn-total", type=float, default=200.0)
    parser.add_argument("--max-tool-cost-mix-ratio", type=float, default=0.80)
    parser.add_argument("--max-stale-days", type=float, default=8.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_days=max(1, int(args.window_days)),
        limit=max(1, int(args.limit)),
    )

    summary = summarize_unit_economics(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_resolution_rate=max(0.0, float(args.min_resolution_rate)),
        max_cost_per_resolved_session=max(0.0, float(args.max_cost_per_resolved_session)),
        max_unresolved_cost_burn_total=max(0.0, float(args.max_unresolved_cost_burn_total)),
        max_tool_cost_mix_ratio=max(0.0, float(args.max_tool_cost_mix_ratio)),
        max_stale_days=max(0.0, float(args.max_stale_days)),
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
                "min_resolution_rate": float(args.min_resolution_rate),
                "max_cost_per_resolved_session": float(args.max_cost_per_resolved_session),
                "max_unresolved_cost_burn_total": float(args.max_unresolved_cost_burn_total),
                "max_tool_cost_mix_ratio": float(args.max_tool_cost_mix_ratio),
                "max_stale_days": float(args.max_stale_days),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"cost_per_resolved_session={_safe_float(summary.get('cost_per_resolved_session'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
