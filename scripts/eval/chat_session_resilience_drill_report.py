#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REQUIRED_SCENARIOS = {"CONNECTION_STORM", "PARTIAL_REGION_FAIL", "BROKER_DELAY"}


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
    for key in ("timestamp", "event_time", "ts", "started_at", "created_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _scenario(row: Mapping[str, Any]) -> str:
    text = str(row.get("scenario") or row.get("scenario_type") or "UNKNOWN").strip().upper()
    aliases = {
        "CONNECTION_STORM": "CONNECTION_STORM",
        "STORM": "CONNECTION_STORM",
        "PARTIAL_REGION_FAIL": "PARTIAL_REGION_FAIL",
        "REGION_FAIL": "PARTIAL_REGION_FAIL",
        "BROKER_DELAY": "BROKER_DELAY",
        "BROKER_LAG": "BROKER_DELAY",
    }
    return aliases.get(text, text or "UNKNOWN")


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


def summarize_drills(events: list[Mapping[str, Any]], *, required_scenarios: set[str], now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    scenario_rows: dict[str, dict[str, Any]] = {}
    open_drill_total = 0
    success_total = 0
    failure_total = 0
    message_loss_total = 0
    message_total = 0
    rto_samples: list[float] = []

    latest_ts: datetime | None = None

    for row in events:
        scenario = _scenario(row)
        status = str(row.get("status") or "UNKNOWN").strip().upper()
        completed = _safe_bool(row.get("completed"), status in {"PASS", "SUCCESS", "DONE"})
        passed = _safe_bool(row.get("passed"), status in {"PASS", "SUCCESS"})
        rto_sec = max(0.0, _safe_float(row.get("rto_sec"), 0.0))
        sent_total = max(0, _safe_int(row.get("sent_total"), 0))
        loss_total = max(0, _safe_int(row.get("message_loss_total"), 0))
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        scenario_row = scenario_rows.setdefault(
            scenario,
            {
                "scenario": scenario,
                "run_total": 0,
                "success_total": 0,
                "failure_total": 0,
                "open_total": 0,
                "avg_rto_sec": 0.0,
                "max_rto_sec": 0.0,
                "message_loss_total": 0,
                "message_total": 0,
            },
        )
        scenario_row["run_total"] += 1
        scenario_row["message_loss_total"] += loss_total
        scenario_row["message_total"] += sent_total

        message_loss_total += loss_total
        message_total += sent_total

        if completed and passed:
            success_total += 1
            scenario_row["success_total"] += 1
            if rto_sec > 0:
                rto_samples.append(rto_sec)
                scenario_row["max_rto_sec"] = max(float(scenario_row.get("max_rto_sec") or 0.0), rto_sec)
                prev_avg = _safe_float(scenario_row.get("avg_rto_sec"), 0.0)
                succ = int(scenario_row.get("success_total") or 1)
                scenario_row["avg_rto_sec"] = prev_avg + (rto_sec - prev_avg) / max(1, succ)
        elif completed and not passed:
            failure_total += 1
            scenario_row["failure_total"] += 1
        else:
            open_drill_total += 1
            scenario_row["open_total"] += 1

    scenario_list = [
        {
            "scenario": row["scenario"],
            "run_total": int(row["run_total"]),
            "success_total": int(row["success_total"]),
            "failure_total": int(row["failure_total"]),
            "open_total": int(row["open_total"]),
            "avg_rto_sec": float(row["avg_rto_sec"]),
            "max_rto_sec": float(row["max_rto_sec"]),
            "message_loss_total": int(row["message_loss_total"]),
            "message_total": int(row["message_total"]),
            "message_loss_ratio": 0.0
            if int(row["message_total"]) == 0
            else float(int(row["message_loss_total"])) / float(int(row["message_total"])),
        }
        for row in sorted(scenario_rows.values(), key=lambda item: item["scenario"])
    ]

    present_scenarios = {item["scenario"] for item in scenario_list}
    missing_required = sorted(required_scenarios - present_scenarios)

    avg_rto_sec = 0.0 if not rto_samples else float(sum(rto_samples)) / float(len(rto_samples))
    max_rto_sec = max(rto_samples) if rto_samples else 0.0
    message_loss_ratio = 0.0 if message_total == 0 else float(message_loss_total) / float(message_total)

    stale_days = 0.0
    if latest_ts is not None:
        stale_days = max(0.0, (now_dt - latest_ts).total_seconds() / 86400.0)

    return {
        "window_size": len(events),
        "scenario_total": len(scenario_list),
        "success_total": success_total,
        "failure_total": failure_total,
        "open_drill_total": open_drill_total,
        "success_ratio": 0.0 if len(events) == 0 else float(success_total) / float(len(events)),
        "avg_rto_sec": avg_rto_sec,
        "max_rto_sec": max_rto_sec,
        "message_loss_total": message_loss_total,
        "message_total": message_total,
        "message_loss_ratio": message_loss_ratio,
        "missing_required_scenarios": missing_required,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_days": stale_days,
        "scenarios": scenario_list,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_open_drill_total: int,
    max_avg_rto_sec: float,
    max_message_loss_ratio: float,
    require_scenarios: bool,
    max_stale_days: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    open_drill_total = _safe_int(summary.get("open_drill_total"), 0)
    avg_rto_sec = _safe_float(summary.get("avg_rto_sec"), 0.0)
    message_loss_ratio = _safe_float(summary.get("message_loss_ratio"), 0.0)
    stale_days = _safe_float(summary.get("stale_days"), 0.0)
    missing = summary.get("missing_required_scenarios") if isinstance(summary.get("missing_required_scenarios"), list) else []

    if window_size < max(0, int(min_window)):
        failures.append(f"drill window too small: {window_size} < {int(min_window)}")
    if open_drill_total > max(0, int(max_open_drill_total)):
        failures.append(f"open drill count exceeded: {open_drill_total} > {int(max_open_drill_total)}")
    if avg_rto_sec > max(0.0, float(max_avg_rto_sec)):
        failures.append(f"average RTO exceeded: {avg_rto_sec:.1f} > {float(max_avg_rto_sec):.1f}")
    if message_loss_ratio > max(0.0, float(max_message_loss_ratio)):
        failures.append(
            f"message loss ratio exceeded: {message_loss_ratio:.6f} > {float(max_message_loss_ratio):.6f}"
        )
    if require_scenarios and missing:
        failures.append(f"required scenarios missing: {', '.join([str(item) for item in missing])}")
    if stale_days > max(0.0, float(max_stale_days)):
        failures.append(f"drill evidence stale: {stale_days:.2f}d > {float(max_stale_days):.2f}d")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Session Resilience Drill Report")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- success_ratio: {_safe_float(summary.get('success_ratio'), 0.0):.4f}")
    lines.append(f"- open_drill_total: {_safe_int(summary.get('open_drill_total'), 0)}")
    lines.append(f"- avg_rto_sec: {_safe_float(summary.get('avg_rto_sec'), 0.0):.1f}")
    lines.append(f"- message_loss_ratio: {_safe_float(summary.get('message_loss_ratio'), 0.0):.6f}")
    lines.append(f"- missing_required_scenarios: {summary.get('missing_required_scenarios')}")

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


def _parse_required_scenarios(raw: str) -> set[str]:
    values = {item.strip().upper() for item in str(raw or "").split(",") if item.strip()}
    return values if values else set(REQUIRED_SCENARIOS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate resilience drill report for chat session gateway failures.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/session_resilience_drills.jsonl")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--required-scenarios", default=",".join(sorted(REQUIRED_SCENARIOS)))
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_session_resilience_drill_report")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-open-drill-total", type=int, default=0)
    parser.add_argument("--max-avg-rto-sec", type=float, default=900.0)
    parser.add_argument("--max-message-loss-ratio", type=float, default=0.001)
    parser.add_argument("--max-stale-days", type=float, default=35.0)
    parser.add_argument("--require-scenarios", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    required_scenarios = _parse_required_scenarios(args.required_scenarios)

    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_days=max(1, int(args.window_days)),
        limit=max(1, int(args.limit)),
    )

    summary = summarize_drills(events, required_scenarios=required_scenarios)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_open_drill_total=max(0, int(args.max_open_drill_total)),
        max_avg_rto_sec=max(0.0, float(args.max_avg_rto_sec)),
        max_message_loss_ratio=max(0.0, float(args.max_message_loss_ratio)),
        require_scenarios=bool(args.require_scenarios),
        max_stale_days=max(0.0, float(args.max_stale_days)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "required_scenarios": sorted(required_scenarios),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_open_drill_total": int(args.max_open_drill_total),
                "max_avg_rto_sec": float(args.max_avg_rto_sec),
                "max_message_loss_ratio": float(args.max_message_loss_ratio),
                "max_stale_days": float(args.max_stale_days),
                "require_scenarios": bool(args.require_scenarios),
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
    print(f"avg_rto_sec={_safe_float(summary.get('avg_rto_sec'), 0.0):.1f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
