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


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * min(1.0, max(0.0, ratio))))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


def _normalize_scenario(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"NORMAL", "PROMOTION", "INCIDENT"}:
        return text
    if text in {"PROMO", "SALE", "EVENT"}:
        return "PROMOTION"
    if text in {"DEGRADE", "OUTAGE", "FAILURE"}:
        return "INCIDENT"
    return "NORMAL" if not text else "UNKNOWN"


def _is_error(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in {"error", "failed", "timeout"}:
        return True
    return _safe_bool(row.get("is_error"), False)


def _tool_calls(row: Mapping[str, Any]) -> int:
    if row.get("tool_calls") is not None:
        return max(0, _safe_int(row.get("tool_calls"), 0))
    if _safe_bool(row.get("tool_called"), False):
        return 1
    return 0


def build_load_profile(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    scenario_rows: dict[str, dict[str, Any]] = {}
    hourly_rows: dict[int, dict[str, float]] = {}
    intent_counts: dict[str, int] = {}

    for row in events:
        ts = _event_ts(row)
        scenario = _normalize_scenario(row.get("scenario"))
        intent = str(row.get("intent") or "UNKNOWN").strip().upper() or "UNKNOWN"
        latency_ms = max(0.0, _safe_float(row.get("latency_ms"), 0.0))
        queue_depth = max(0, _safe_int(row.get("queue_depth"), 0))
        tool_calls = _tool_calls(row)
        token_total = max(0, _safe_int(row.get("tokens"), 0))
        is_error = _is_error(row)

        scenario_row = scenario_rows.setdefault(
            scenario,
            {
                "request_total": 0,
                "error_total": 0,
                "tool_call_total": 0,
                "tool_used_total": 0,
                "token_total": 0,
                "latency_samples": [],
                "queue_samples": [],
            },
        )
        scenario_row["request_total"] += 1
        scenario_row["token_total"] += token_total
        scenario_row["tool_call_total"] += tool_calls
        if tool_calls > 0:
            scenario_row["tool_used_total"] += 1
        if is_error:
            scenario_row["error_total"] += 1
        scenario_row["latency_samples"].append(latency_ms)
        scenario_row["queue_samples"].append(float(queue_depth))

        if ts is not None:
            hour = int(ts.hour)
            hour_row = hourly_rows.setdefault(hour, {"request_total": 0.0, "token_total": 0.0, "error_total": 0.0})
            hour_row["request_total"] += 1.0
            hour_row["token_total"] += float(token_total)
            if is_error:
                hour_row["error_total"] += 1.0

        intent_counts[intent] = intent_counts.get(intent, 0) + 1

    profiles: dict[str, dict[str, Any]] = {}
    for scenario, row in scenario_rows.items():
        total = int(row.get("request_total") or 0)
        error_total = int(row.get("error_total") or 0)
        tool_used_total = int(row.get("tool_used_total") or 0)
        tool_call_total = int(row.get("tool_call_total") or 0)
        token_total = int(row.get("token_total") or 0)
        latency_samples = [float(item) for item in row.get("latency_samples") or []]
        queue_samples = [float(item) for item in row.get("queue_samples") or []]

        profiles[scenario] = {
            "request_total": total,
            "error_total": error_total,
            "error_ratio": 0.0 if total == 0 else float(error_total) / float(total),
            "tool_usage_ratio": 0.0 if total == 0 else float(tool_used_total) / float(total),
            "tool_calls_per_request": 0.0 if total == 0 else float(tool_call_total) / float(total),
            "avg_tokens": 0.0 if total == 0 else float(token_total) / float(total),
            "p95_latency_ms": _percentile(latency_samples, 0.95),
            "p95_queue_depth": _percentile(queue_samples, 0.95),
        }

    hourly_profile = [
        {
            "hour_utc": hour,
            "request_total": int(values["request_total"]),
            "error_ratio": 0.0 if values["request_total"] <= 0 else float(values["error_total"]) / float(values["request_total"]),
            "avg_tokens": 0.0 if values["request_total"] <= 0 else float(values["token_total"]) / float(values["request_total"]),
        }
        for hour, values in sorted(hourly_rows.items(), key=lambda item: item[0])
    ]

    intents = [
        {"intent": intent, "count": count}
        for intent, count in sorted(intent_counts.items(), key=lambda item: item[1], reverse=True)[:20]
    ]

    normal = profiles.get("NORMAL", {})
    promotion = profiles.get("PROMOTION", {})
    incident = profiles.get("INCIDENT", {})

    return {
        "window_size": len(events),
        "profiles": profiles,
        "hourly_profile": hourly_profile,
        "intent_distribution": intents,
        "derived": {
            "normal_request_total": int(normal.get("request_total") or 0),
            "promotion_request_total": int(promotion.get("request_total") or 0),
            "incident_request_total": int(incident.get("request_total") or 0),
            "promotion_vs_normal_ratio": 0.0
            if int(normal.get("request_total") or 0) <= 0
            else float(int(promotion.get("request_total") or 0)) / float(int(normal.get("request_total") or 0)),
            "incident_vs_normal_ratio": 0.0
            if int(normal.get("request_total") or 0) <= 0
            else float(int(incident.get("request_total") or 0)) / float(int(normal.get("request_total") or 0)),
        },
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_normal_error_ratio: float,
    max_normal_p95_latency_ms: float,
    max_normal_p95_queue_depth: float,
) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    profiles = summary.get("profiles") if isinstance(summary.get("profiles"), Mapping) else {}
    normal = profiles.get("NORMAL") if isinstance(profiles.get("NORMAL"), Mapping) else {}

    normal_error_ratio = _safe_float(normal.get("error_ratio"), 0.0)
    normal_p95_latency_ms = _safe_float(normal.get("p95_latency_ms"), 0.0)
    normal_p95_queue_depth = _safe_float(normal.get("p95_queue_depth"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"load model window too small: {window_size} < {int(min_window)}")
    if normal_error_ratio > max(0.0, float(max_normal_error_ratio)):
        failures.append(
            f"normal error ratio exceeded: {normal_error_ratio:.4f} > {float(max_normal_error_ratio):.4f}"
        )
    if normal_p95_latency_ms > max(0.0, float(max_normal_p95_latency_ms)):
        failures.append(
            f"normal p95 latency exceeded: {normal_p95_latency_ms:.1f} > {float(max_normal_p95_latency_ms):.1f}"
        )
    if normal_p95_queue_depth > max(0.0, float(max_normal_p95_queue_depth)):
        failures.append(
            f"normal p95 queue depth exceeded: {normal_p95_queue_depth:.1f} > {float(max_normal_p95_queue_depth):.1f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    derived = summary.get("derived") if isinstance(summary.get("derived"), Mapping) else {}
    profiles = summary.get("profiles") if isinstance(summary.get("profiles"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Load Profile Model")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- traffic_jsonl: {payload.get('traffic_jsonl')}")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- promotion_vs_normal_ratio: {_safe_float(derived.get('promotion_vs_normal_ratio'), 0.0):.4f}")
    lines.append(f"- incident_vs_normal_ratio: {_safe_float(derived.get('incident_vs_normal_ratio'), 0.0):.4f}")
    lines.append("")
    lines.append("## Scenario Profiles")
    lines.append("")
    for scenario in ("NORMAL", "PROMOTION", "INCIDENT", "UNKNOWN"):
        profile = profiles.get(scenario) if isinstance(profiles.get(scenario), Mapping) else {}
        if not profile:
            continue
        lines.append(
            "- "
            f"{scenario}: requests={int(profile.get('request_total') or 0)} "
            f"error_ratio={_safe_float(profile.get('error_ratio'), 0.0):.4f} "
            f"tool_usage_ratio={_safe_float(profile.get('tool_usage_ratio'), 0.0):.4f} "
            f"p95_latency_ms={_safe_float(profile.get('p95_latency_ms'), 0.0):.1f} "
            f"p95_queue_depth={_safe_float(profile.get('p95_queue_depth'), 0.0):.1f}"
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
    parser = argparse.ArgumentParser(description="Build chat traffic load profiles by scenario/intent/hour.")
    parser.add_argument("--traffic-jsonl", default="var/chat_governance/load_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=168)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_load_profile_model")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-normal-error-ratio", type=float, default=0.05)
    parser.add_argument("--max-normal-p95-latency-ms", type=float, default=3000.0)
    parser.add_argument("--max-normal-p95-queue-depth", type=float, default=50.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    traffic_path = Path(args.traffic_jsonl)
    events = read_events(
        traffic_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )

    summary = build_load_profile(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_normal_error_ratio=max(0.0, float(args.max_normal_error_ratio)),
        max_normal_p95_latency_ms=max(0.0, float(args.max_normal_p95_latency_ms)),
        max_normal_p95_queue_depth=max(0.0, float(args.max_normal_p95_queue_depth)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "traffic_jsonl": str(traffic_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_normal_error_ratio": float(args.max_normal_error_ratio),
                "max_normal_p95_latency_ms": float(args.max_normal_p95_latency_ms),
                "max_normal_p95_queue_depth": float(args.max_normal_p95_queue_depth),
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
    print(f"window_size={int(summary.get('window_size') or 0)}")
    print(
        "normal_error_ratio="
        f"{_safe_float((summary.get('profiles') or {}).get('NORMAL', {}).get('error_ratio'), 0.0):.4f}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
