#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_RISKS = {"LOW", "MEDIUM", "HIGH"}


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


def _normalize_risk(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "L": "LOW",
        "M": "MEDIUM",
        "H": "HIGH",
        "WRITE": "MEDIUM",
        "WRITE_SENSITIVE": "HIGH",
    }
    if text in VALID_RISKS:
        return text
    return aliases.get(text, text or "UNKNOWN")


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


def summarize_risk_classification(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    action_total = 0
    unknown_risk_total = 0
    high_risk_without_stepup_total = 0
    irreversible_not_high_risk_total = 0
    missing_actor_total = 0
    missing_target_total = 0
    risk_distribution: dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "UNKNOWN": 0}

    for row in events:
        action_total += 1
        risk = _normalize_risk(row.get("risk_level") or row.get("risk"))
        stepup_required = _safe_bool(row.get("stepup_required") or row.get("requires_stepup_auth"), False)
        irreversible = _safe_bool(row.get("irreversible") or row.get("is_irreversible"), False)
        actor = str(row.get("actor_id") or row.get("user_id") or "").strip()
        target = str(row.get("target_id") or row.get("order_id") or row.get("action_target") or "").strip()

        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if risk in VALID_RISKS:
            risk_distribution[risk] += 1
        else:
            unknown_risk_total += 1
            risk_distribution["UNKNOWN"] += 1

        if risk == "HIGH" and not stepup_required:
            high_risk_without_stepup_total += 1
        if irreversible and risk != "HIGH":
            irreversible_not_high_risk_total += 1
        if not actor:
            missing_actor_total += 1
        if not target:
            missing_target_total += 1

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "action_total": action_total,
        "unknown_risk_total": unknown_risk_total,
        "high_risk_without_stepup_total": high_risk_without_stepup_total,
        "irreversible_not_high_risk_total": irreversible_not_high_risk_total,
        "missing_actor_total": missing_actor_total,
        "missing_target_total": missing_target_total,
        "risk_distribution": risk_distribution,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_unknown_risk_total: int,
    max_high_risk_without_stepup_total: int,
    max_irreversible_not_high_risk_total: int,
    max_missing_actor_total: int,
    max_missing_target_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    unknown_risk_total = _safe_int(summary.get("unknown_risk_total"), 0)
    high_risk_without_stepup_total = _safe_int(summary.get("high_risk_without_stepup_total"), 0)
    irreversible_not_high_risk_total = _safe_int(summary.get("irreversible_not_high_risk_total"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    missing_target_total = _safe_int(summary.get("missing_target_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"sensitive action risk window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if unknown_risk_total > max(0, int(max_unknown_risk_total)):
        failures.append(f"unknown risk level total exceeded: {unknown_risk_total} > {int(max_unknown_risk_total)}")
    if high_risk_without_stepup_total > max(0, int(max_high_risk_without_stepup_total)):
        failures.append(
            "high risk without step-up total exceeded: "
            f"{high_risk_without_stepup_total} > {int(max_high_risk_without_stepup_total)}"
        )
    if irreversible_not_high_risk_total > max(0, int(max_irreversible_not_high_risk_total)):
        failures.append(
            "irreversible action not classified HIGH exceeded: "
            f"{irreversible_not_high_risk_total} > {int(max_irreversible_not_high_risk_total)}"
        )
    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if missing_target_total > max(0, int(max_missing_target_total)):
        failures.append(f"missing target total exceeded: {missing_target_total} > {int(max_missing_target_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"sensitive action risk events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Sensitive Action Risk Classification")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- action_total: {_safe_int(summary.get('action_total'), 0)}")
    lines.append(f"- unknown_risk_total: {_safe_int(summary.get('unknown_risk_total'), 0)}")
    lines.append(
        f"- high_risk_without_stepup_total: {_safe_int(summary.get('high_risk_without_stepup_total'), 0)}"
    )
    lines.append(
        f"- irreversible_not_high_risk_total: {_safe_int(summary.get('irreversible_not_high_risk_total'), 0)}"
    )
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
    parser = argparse.ArgumentParser(description="Evaluate sensitive-action risk classification policy quality.")
    parser.add_argument("--events-jsonl", default="var/chat_actions/sensitive_action_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_sensitive_action_risk_classification")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-unknown-risk-total", type=int, default=0)
    parser.add_argument("--max-high-risk-without-stepup-total", type=int, default=0)
    parser.add_argument("--max-irreversible-not-high-risk-total", type=int, default=0)
    parser.add_argument("--max-missing-actor-total", type=int, default=0)
    parser.add_argument("--max-missing-target-total", type=int, default=0)
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
    summary = summarize_risk_classification(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_unknown_risk_total=max(0, int(args.max_unknown_risk_total)),
        max_high_risk_without_stepup_total=max(0, int(args.max_high_risk_without_stepup_total)),
        max_irreversible_not_high_risk_total=max(0, int(args.max_irreversible_not_high_risk_total)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_missing_target_total=max(0, int(args.max_missing_target_total)),
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
                "max_unknown_risk_total": int(args.max_unknown_risk_total),
                "max_high_risk_without_stepup_total": int(args.max_high_risk_without_stepup_total),
                "max_irreversible_not_high_risk_total": int(args.max_irreversible_not_high_risk_total),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_missing_target_total": int(args.max_missing_target_total),
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
    print(f"action_total={_safe_int(summary.get('action_total'), 0)}")
    print(f"unknown_risk_total={_safe_int(summary.get('unknown_risk_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
