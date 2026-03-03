#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROUTED_RESULTS = {"ROUTED", "EXECUTE", "TOOL", "SELECTED", "ALLOW"}
FALLBACK_RESULTS = {"FALLBACK", "HANDOFF", "CLARIFY", "ASK", "OPEN_TICKET"}
CAPABILITY_MISS_RESULTS = {"CAPABILITY_MISS", "NO_CAPABILITY", "UNSUPPORTED_INTENT"}
NO_CANDIDATE_RESULTS = {"NO_CANDIDATE", "NO_CAPABILITY", "CAPABILITY_MISS", "UNSUPPORTED_INTENT"}


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


def _route_result(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("route_result") or row.get("route_decision") or row.get("result"))


def _selected_tool(row: Mapping[str, Any]) -> str:
    return str(row.get("selected_tool") or row.get("route_tool") or row.get("tool") or "").strip()


def _capability_match(row: Mapping[str, Any], *, selected_tool: str, result: str) -> bool:
    explicit = _safe_bool(row.get("capability_match"))
    if explicit is not None:
        return explicit
    if result in CAPABILITY_MISS_RESULTS:
        return False
    if selected_tool:
        return True
    return False


def _fallback_applied(row: Mapping[str, Any], *, result: str) -> bool:
    explicit = _safe_bool(row.get("fallback_applied"))
    if explicit is not None:
        return explicit
    return result in FALLBACK_RESULTS


def summarize_tool_capability_routing_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    route_event_total = 0
    routed_total = 0
    capability_match_total = 0
    capability_miss_total = 0
    below_health_routed_total = 0
    intent_without_candidate_total = 0
    fallback_route_total = 0
    distribution: dict[tuple[str, str, str], int] = {}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        intent = _normalize_token(row.get("intent") or row.get("predicted_intent") or "UNKNOWN")
        result = _route_result(row)
        selected_tool = _selected_tool(row)

        route_event_total += 1
        if selected_tool:
            routed_total += 1

        capability_match = _capability_match(row, selected_tool=selected_tool, result=result)
        if selected_tool and capability_match:
            capability_match_total += 1

        capability_miss = (selected_tool and not capability_match) or result in CAPABILITY_MISS_RESULTS
        if capability_miss:
            capability_miss_total += 1

        health_score = _safe_float(
            row.get("selected_tool_health_score")
            if row.get("selected_tool_health_score") is not None
            else row.get("tool_health_score"),
            1.0,
        )
        health_threshold = _safe_float(row.get("tool_health_threshold") or row.get("min_tool_health_score"), 0.0)
        if selected_tool and (result in ROUTED_RESULTS or not result) and health_score < health_threshold:
            below_health_routed_total += 1

        if (not selected_tool) and result in NO_CANDIDATE_RESULTS:
            intent_without_candidate_total += 1

        if _fallback_applied(row, result=result):
            fallback_route_total += 1

        distribution[(intent, selected_tool or "NONE", result or "UNKNOWN")] = distribution.get(
            (intent, selected_tool or "NONE", result or "UNKNOWN"), 0
        ) + 1

    capability_match_ratio = 1.0 if routed_total == 0 else float(capability_match_total) / float(routed_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    route_distribution = [
        {"intent": intent, "tool": tool, "result": result, "count": count}
        for (intent, tool, result), count in sorted(distribution.items(), key=lambda item: item[0])
    ]

    return {
        "window_size": len(rows),
        "route_event_total": route_event_total,
        "routed_total": routed_total,
        "capability_match_total": capability_match_total,
        "capability_match_ratio": capability_match_ratio,
        "capability_miss_total": capability_miss_total,
        "below_health_routed_total": below_health_routed_total,
        "intent_without_candidate_total": intent_without_candidate_total,
        "fallback_route_total": fallback_route_total,
        "route_distribution": route_distribution,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_route_event_total: int,
    min_capability_match_ratio: float,
    max_capability_miss_total: int,
    max_below_health_routed_total: int,
    max_intent_without_candidate_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    route_event_total = _safe_int(summary.get("route_event_total"), 0)
    capability_match_ratio = _safe_float(summary.get("capability_match_ratio"), 0.0)
    capability_miss_total = _safe_int(summary.get("capability_miss_total"), 0)
    below_health_routed_total = _safe_int(summary.get("below_health_routed_total"), 0)
    intent_without_candidate_total = _safe_int(summary.get("intent_without_candidate_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool capability routing window too small: {window_size} < {int(min_window)}")
    if route_event_total < max(0, int(min_route_event_total)):
        failures.append(
            f"tool capability routing event total too small: {route_event_total} < {int(min_route_event_total)}"
        )
    if window_size == 0:
        return failures

    if capability_match_ratio < max(0.0, float(min_capability_match_ratio)):
        failures.append(
            f"tool capability routing match ratio below minimum: {capability_match_ratio:.4f} < {float(min_capability_match_ratio):.4f}"
        )
    if capability_miss_total > max(0, int(max_capability_miss_total)):
        failures.append(
            f"tool capability routing miss total exceeded: {capability_miss_total} > {int(max_capability_miss_total)}"
        )
    if below_health_routed_total > max(0, int(max_below_health_routed_total)):
        failures.append(
            f"tool capability routing below-health routed total exceeded: {below_health_routed_total} > {int(max_below_health_routed_total)}"
        )
    if intent_without_candidate_total > max(0, int(max_intent_without_candidate_total)):
        failures.append(
            f"tool capability routing intent-without-candidate total exceeded: {intent_without_candidate_total} > {int(max_intent_without_candidate_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool capability routing stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Capability Routing Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- route_event_total: {_safe_int(summary.get('route_event_total'), 0)}")
    lines.append(f"- capability_match_ratio: {_safe_float(summary.get('capability_match_ratio'), 0.0):.4f}")
    lines.append(f"- capability_miss_total: {_safe_int(summary.get('capability_miss_total'), 0)}")
    lines.append(f"- below_health_routed_total: {_safe_int(summary.get('below_health_routed_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate capability-aware tool routing quality.")
    parser.add_argument("--events-jsonl", default="var/tool_health/capability_routing_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_capability_routing_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-route-event-total", type=int, default=0)
    parser.add_argument("--min-capability-match-ratio", type=float, default=0.0)
    parser.add_argument("--max-capability-miss-total", type=int, default=1000000)
    parser.add_argument("--max-below-health-routed-total", type=int, default=1000000)
    parser.add_argument("--max-intent-without-candidate-total", type=int, default=1000000)
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
    summary = summarize_tool_capability_routing_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_route_event_total=max(0, int(args.min_route_event_total)),
        min_capability_match_ratio=max(0.0, float(args.min_capability_match_ratio)),
        max_capability_miss_total=max(0, int(args.max_capability_miss_total)),
        max_below_health_routed_total=max(0, int(args.max_below_health_routed_total)),
        max_intent_without_candidate_total=max(0, int(args.max_intent_without_candidate_total)),
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
                "min_route_event_total": int(args.min_route_event_total),
                "min_capability_match_ratio": float(args.min_capability_match_ratio),
                "max_capability_miss_total": int(args.max_capability_miss_total),
                "max_below_health_routed_total": int(args.max_below_health_routed_total),
                "max_intent_without_candidate_total": int(args.max_intent_without_candidate_total),
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
    print(f"route_event_total={_safe_int(summary.get('route_event_total'), 0)}")
    print(f"capability_match_ratio={_safe_float(summary.get('capability_match_ratio'), 0.0):.4f}")
    print(f"capability_miss_total={_safe_int(summary.get('capability_miss_total'), 0)}")
    print(f"below_health_routed_total={_safe_int(summary.get('below_health_routed_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
