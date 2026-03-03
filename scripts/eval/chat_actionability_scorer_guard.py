#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


INTENT_CUTLINES: dict[str, float] = {
    "ORDER": 0.75,
    "SHIPPING": 0.75,
    "REFUND": 0.85,
    "GENERAL": 0.60,
}

COMPONENT_NAMES = (
    "current_state",
    "next_action",
    "expected_outcome",
    "fallback_alternative",
)


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


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


def _intent_bucket(row: Mapping[str, Any]) -> str:
    raw = str(row.get("intent") or row.get("intent_name") or row.get("intent_bucket") or "").upper()
    if "REFUND" in raw or "RETURN" in raw:
        return "REFUND"
    if "SHIP" in raw or "DELIVERY" in raw or "TRACK" in raw:
        return "SHIPPING"
    if "ORDER" in raw or "CANCEL" in raw or "PAY" in raw:
        return "ORDER"
    return "GENERAL"


def _text_present(value: Any) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def _component_present(row: Mapping[str, Any], component: str) -> bool:
    if component == "current_state":
        return (
            _safe_bool(row.get("has_current_state"))
            or _safe_bool(row.get("current_state_present"))
            or _text_present(row.get("current_state"))
            or _text_present(row.get("state_summary"))
        )
    if component == "next_action":
        action_text = str(row.get("next_action") or "").strip().upper()
        return (
            _safe_bool(row.get("has_next_action"))
            or _safe_bool(row.get("next_action_present"))
            or (_text_present(row.get("next_action")) and action_text not in {"NONE", "UNKNOWN"})
            or _text_present(row.get("suggested_action"))
        )
    if component == "expected_outcome":
        return (
            _safe_bool(row.get("has_expected_outcome"))
            or _safe_bool(row.get("expected_outcome_present"))
            or _text_present(row.get("expected_outcome"))
            or _text_present(row.get("expected_result"))
        )
    if component == "fallback_alternative":
        alternatives = row.get("alternative_paths")
        has_alternatives = isinstance(alternatives, list) and any(_text_present(item) for item in alternatives)
        return (
            _safe_bool(row.get("has_fallback_alternative"))
            or _safe_bool(row.get("fallback_alternative_present"))
            or has_alternatives
            or _text_present(row.get("fallback_action"))
            or _text_present(row.get("fail_closed_action"))
        )
    return False


def _normalize_score(value: Any) -> float | None:
    if value is None:
        return None
    score = _safe_float(value, -1.0)
    if score < 0.0:
        return None
    if score > 1.0:
        if score <= 100.0:
            score = score / 100.0
        else:
            score = 1.0
    return max(0.0, min(1.0, score))


def _score_bucket(score: float) -> str:
    pct = score * 100.0
    if pct < 40.0:
        return "lt40"
    if pct < 60.0:
        return "40_59"
    if pct < 80.0:
        return "60_79"
    return "80_100"


def summarize_actionability_scorer_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    scored_total = 0
    low_actionability_total = 0
    score_sum = 0.0
    score_hist = {"lt40": 0, "40_59": 0, "60_79": 0, "80_100": 0}
    low_actionability_by_intent = {"ORDER": 0, "SHIPPING": 0, "REFUND": 0, "GENERAL": 0}
    missing_components_total = {name: 0 for name in COMPONENT_NAMES}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        components = {name: _component_present(row, name) for name in COMPONENT_NAMES}
        for name, present in components.items():
            if not present:
                missing_components_total[name] += 1

        explicit = _normalize_score(row.get("actionability_score"))
        if explicit is None:
            explicit = _normalize_score(row.get("score"))
        if explicit is None:
            present_count = sum(1 for present in components.values() if present)
            explicit = float(present_count) / float(len(COMPONENT_NAMES))
        score = explicit

        scored_total += 1
        score_sum += score
        score_hist[_score_bucket(score)] += 1

        bucket = _intent_bucket(row)
        cutline = INTENT_CUTLINES.get(bucket, INTENT_CUTLINES["GENERAL"])
        if score < cutline:
            low_actionability_total += 1
            low_actionability_by_intent[bucket] = _safe_int(low_actionability_by_intent.get(bucket), 0) + 1

    average_score = 0.0 if scored_total == 0 else score_sum / float(scored_total)
    low_actionability_ratio = 0.0 if scored_total == 0 else float(low_actionability_total) / float(scored_total)

    missing_component_ratios: dict[str, float] = {}
    for name in COMPONENT_NAMES:
        missing_component_ratios[name] = 0.0 if event_total == 0 else float(missing_components_total[name]) / float(event_total)

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "scored_total": scored_total,
        "average_actionability_score": average_score,
        "score_hist": score_hist,
        "low_actionability_total": low_actionability_total,
        "low_actionability_ratio": low_actionability_ratio,
        "low_actionability_by_intent": low_actionability_by_intent,
        "missing_current_state_total": missing_components_total["current_state"],
        "missing_next_action_total": missing_components_total["next_action"],
        "missing_expected_outcome_total": missing_components_total["expected_outcome"],
        "missing_fallback_alternative_total": missing_components_total["fallback_alternative"],
        "missing_current_state_ratio": missing_component_ratios["current_state"],
        "missing_next_action_ratio": missing_component_ratios["next_action"],
        "missing_expected_outcome_ratio": missing_component_ratios["expected_outcome"],
        "missing_fallback_alternative_ratio": missing_component_ratios["fallback_alternative"],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_average_actionability_score: float,
    max_low_actionability_ratio: float,
    max_low_actionability_total: int,
    max_missing_current_state_ratio: float,
    max_missing_next_action_ratio: float,
    max_missing_expected_outcome_ratio: float,
    max_missing_fallback_alternative_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    average_score = _safe_float(summary.get("average_actionability_score"), 0.0)
    low_ratio = _safe_float(summary.get("low_actionability_ratio"), 0.0)
    low_total = _safe_int(summary.get("low_actionability_total"), 0)
    missing_current_state_ratio = _safe_float(summary.get("missing_current_state_ratio"), 0.0)
    missing_next_action_ratio = _safe_float(summary.get("missing_next_action_ratio"), 0.0)
    missing_expected_outcome_ratio = _safe_float(summary.get("missing_expected_outcome_ratio"), 0.0)
    missing_fallback_alternative_ratio = _safe_float(summary.get("missing_fallback_alternative_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"actionability window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"actionability event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if average_score < max(0.0, float(min_average_actionability_score)):
        failures.append(
            "actionability average score below minimum: "
            f"{average_score:.4f} < {float(min_average_actionability_score):.4f}"
        )
    if low_ratio > max(0.0, float(max_low_actionability_ratio)):
        failures.append(
            "actionability low-score ratio exceeded: "
            f"{low_ratio:.4f} > {float(max_low_actionability_ratio):.4f}"
        )
    if low_total > max(0, int(max_low_actionability_total)):
        failures.append(f"actionability low-score total exceeded: {low_total} > {int(max_low_actionability_total)}")
    if missing_current_state_ratio > max(0.0, float(max_missing_current_state_ratio)):
        failures.append(
            "actionability missing-current-state ratio exceeded: "
            f"{missing_current_state_ratio:.4f} > {float(max_missing_current_state_ratio):.4f}"
        )
    if missing_next_action_ratio > max(0.0, float(max_missing_next_action_ratio)):
        failures.append(
            "actionability missing-next-action ratio exceeded: "
            f"{missing_next_action_ratio:.4f} > {float(max_missing_next_action_ratio):.4f}"
        )
    if missing_expected_outcome_ratio > max(0.0, float(max_missing_expected_outcome_ratio)):
        failures.append(
            "actionability missing-expected-outcome ratio exceeded: "
            f"{missing_expected_outcome_ratio:.4f} > {float(max_missing_expected_outcome_ratio):.4f}"
        )
    if missing_fallback_alternative_ratio > max(0.0, float(max_missing_fallback_alternative_ratio)):
        failures.append(
            "actionability missing-fallback-alternative ratio exceeded: "
            f"{missing_fallback_alternative_ratio:.4f} > {float(max_missing_fallback_alternative_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"actionability stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    score_hist = summary.get("score_hist") if isinstance(summary.get("score_hist"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Actionability Scorer Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- average_actionability_score: {_safe_float(summary.get('average_actionability_score'), 0.0):.4f}")
    lines.append(f"- low_actionability_ratio: {_safe_float(summary.get('low_actionability_ratio'), 0.0):.4f}")
    lines.append(
        f"- missing_current_state_ratio: {_safe_float(summary.get('missing_current_state_ratio'), 0.0):.4f}"
    )
    lines.append(f"- missing_next_action_ratio: {_safe_float(summary.get('missing_next_action_ratio'), 0.0):.4f}")
    lines.append(
        f"- missing_expected_outcome_ratio: {_safe_float(summary.get('missing_expected_outcome_ratio'), 0.0):.4f}"
    )
    lines.append(
        "- missing_fallback_alternative_ratio: "
        f"{_safe_float(summary.get('missing_fallback_alternative_ratio'), 0.0):.4f}"
    )
    lines.append(
        "- score_hist: "
        f"lt40={_safe_int(score_hist.get('lt40'), 0)}, "
        f"40_59={_safe_int(score_hist.get('40_59'), 0)}, "
        f"60_79={_safe_int(score_hist.get('60_79'), 0)}, "
        f"80_100={_safe_int(score_hist.get('80_100'), 0)}"
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
    parser = argparse.ArgumentParser(description="Evaluate chat actionability scoring quality.")
    parser.add_argument("--events-jsonl", default="var/actionability/scorer_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_actionability_scorer_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-average-actionability-score", type=float, default=0.0)
    parser.add_argument("--max-low-actionability-ratio", type=float, default=1.0)
    parser.add_argument("--max-low-actionability-total", type=int, default=1000000)
    parser.add_argument("--max-missing-current-state-ratio", type=float, default=1.0)
    parser.add_argument("--max-missing-next-action-ratio", type=float, default=1.0)
    parser.add_argument("--max-missing-expected-outcome-ratio", type=float, default=1.0)
    parser.add_argument("--max-missing-fallback-alternative-ratio", type=float, default=1.0)
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
    summary = summarize_actionability_scorer_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_average_actionability_score=max(0.0, float(args.min_average_actionability_score)),
        max_low_actionability_ratio=max(0.0, float(args.max_low_actionability_ratio)),
        max_low_actionability_total=max(0, int(args.max_low_actionability_total)),
        max_missing_current_state_ratio=max(0.0, float(args.max_missing_current_state_ratio)),
        max_missing_next_action_ratio=max(0.0, float(args.max_missing_next_action_ratio)),
        max_missing_expected_outcome_ratio=max(0.0, float(args.max_missing_expected_outcome_ratio)),
        max_missing_fallback_alternative_ratio=max(0.0, float(args.max_missing_fallback_alternative_ratio)),
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
                "min_average_actionability_score": float(args.min_average_actionability_score),
                "max_low_actionability_ratio": float(args.max_low_actionability_ratio),
                "max_low_actionability_total": int(args.max_low_actionability_total),
                "max_missing_current_state_ratio": float(args.max_missing_current_state_ratio),
                "max_missing_next_action_ratio": float(args.max_missing_next_action_ratio),
                "max_missing_expected_outcome_ratio": float(args.max_missing_expected_outcome_ratio),
                "max_missing_fallback_alternative_ratio": float(args.max_missing_fallback_alternative_ratio),
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
    print(f"average_actionability_score={_safe_float(summary.get('average_actionability_score'), 0.0):.4f}")
    print(f"low_actionability_ratio={_safe_float(summary.get('low_actionability_ratio'), 0.0):.4f}")
    print(f"missing_current_state_ratio={_safe_float(summary.get('missing_current_state_ratio'), 0.0):.4f}")
    print(f"missing_next_action_ratio={_safe_float(summary.get('missing_next_action_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
