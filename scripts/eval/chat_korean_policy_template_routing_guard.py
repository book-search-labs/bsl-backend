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


def _is_korean_event(row: Mapping[str, Any]) -> bool:
    locale = str(row.get("locale") or row.get("user_locale") or "").strip().lower()
    lang = str(row.get("language") or row.get("lang") or "").strip().lower()
    return locale.startswith("ko") or lang in {"ko", "ko-kr", "korean"}


def _template_required(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("template_required"))
    if explicit is not None:
        return explicit
    reason = str(row.get("reason_code") or "").strip()
    return bool(reason)


def _template_key(row: Mapping[str, Any]) -> str:
    return str(row.get("template_key") or row.get("template_id") or row.get("policy_template_key") or "").strip()


def _expected_template_key(row: Mapping[str, Any]) -> str:
    return str(row.get("expected_template_key") or row.get("expected_template_id") or "").strip()


def _template_is_korean(row: Mapping[str, Any]) -> bool:
    lang = str(row.get("template_language") or row.get("template_locale") or "").strip().lower()
    if lang:
        return lang.startswith("ko")
    key = _template_key(row).lower()
    return key.startswith("ko_") or key.endswith("_ko")


def _required_slots(row: Mapping[str, Any]) -> list[str]:
    slots = row.get("required_slots")
    if isinstance(slots, list):
        return [str(slot).strip() for slot in slots if str(slot).strip()]
    text = str(row.get("required_slot_names") or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _rendered_slot_keys(row: Mapping[str, Any]) -> set[str]:
    rendered = row.get("rendered_slots")
    if isinstance(rendered, Mapping):
        return {str(key).strip() for key in rendered.keys() if str(key).strip()}
    if isinstance(rendered, list):
        keys: set[str] = set()
        for item in rendered:
            if isinstance(item, Mapping):
                key = str(item.get("name") or item.get("slot") or "").strip()
                if key:
                    keys.add(key)
            else:
                key = str(item).strip()
                if key:
                    keys.add(key)
        return keys
    text = str(row.get("rendered_slot_names") or "").strip()
    if not text:
        return set()
    return {item.strip() for item in text.split(",") if item.strip()}


def summarize_korean_policy_template_routing_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    korean_event_total = 0
    template_required_total = 0
    routed_total = 0
    missing_template_total = 0
    wrong_template_total = 0
    missing_slot_injection_total = 0
    non_korean_template_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        is_korean = _is_korean_event(row)
        if is_korean:
            korean_event_total += 1

        required = _template_required(row)
        if not required:
            continue
        template_required_total += 1

        template_key = _template_key(row)
        if template_key:
            routed_total += 1
        else:
            missing_template_total += 1
            continue

        expected_key = _expected_template_key(row)
        if expected_key and expected_key != template_key:
            wrong_template_total += 1

        required_slots = _required_slots(row)
        rendered_slots = _rendered_slot_keys(row)
        missing_slots = [slot for slot in required_slots if slot not in rendered_slots]
        if missing_slots:
            missing_slot_injection_total += 1

        if is_korean and not _template_is_korean(row):
            non_korean_template_total += 1

    routing_coverage_ratio = (
        1.0 if template_required_total == 0 else float(routed_total) / float(template_required_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "korean_event_total": korean_event_total,
        "template_required_total": template_required_total,
        "routed_total": routed_total,
        "routing_coverage_ratio": routing_coverage_ratio,
        "missing_template_total": missing_template_total,
        "wrong_template_total": wrong_template_total,
        "missing_slot_injection_total": missing_slot_injection_total,
        "non_korean_template_total": non_korean_template_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_routing_coverage_ratio: float,
    max_missing_template_total: int,
    max_wrong_template_total: int,
    max_missing_slot_injection_total: int,
    max_non_korean_template_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    routing_coverage_ratio = _safe_float(summary.get("routing_coverage_ratio"), 0.0)
    missing_template_total = _safe_int(summary.get("missing_template_total"), 0)
    wrong_template_total = _safe_int(summary.get("wrong_template_total"), 0)
    missing_slot_injection_total = _safe_int(summary.get("missing_slot_injection_total"), 0)
    non_korean_template_total = _safe_int(summary.get("non_korean_template_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"korean policy template window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"korean policy template event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if routing_coverage_ratio < max(0.0, float(min_routing_coverage_ratio)):
        failures.append(
            "korean policy template routing coverage below minimum: "
            f"{routing_coverage_ratio:.4f} < {float(min_routing_coverage_ratio):.4f}"
        )
    if missing_template_total > max(0, int(max_missing_template_total)):
        failures.append(
            f"korean policy template missing-template total exceeded: {missing_template_total} > {int(max_missing_template_total)}"
        )
    if wrong_template_total > max(0, int(max_wrong_template_total)):
        failures.append(
            f"korean policy template wrong-template total exceeded: {wrong_template_total} > {int(max_wrong_template_total)}"
        )
    if missing_slot_injection_total > max(0, int(max_missing_slot_injection_total)):
        failures.append(
            "korean policy template missing-slot-injection total exceeded: "
            f"{missing_slot_injection_total} > {int(max_missing_slot_injection_total)}"
        )
    if non_korean_template_total > max(0, int(max_non_korean_template_total)):
        failures.append(
            "korean policy template non-korean-template total exceeded: "
            f"{non_korean_template_total} > {int(max_non_korean_template_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"korean policy template stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Policy Template Routing Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- template_required_total: {_safe_int(summary.get('template_required_total'), 0)}")
    lines.append(f"- routing_coverage_ratio: {_safe_float(summary.get('routing_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- missing_template_total: {_safe_int(summary.get('missing_template_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate korean policy template routing quality.")
    parser.add_argument("--events-jsonl", default="var/grounded_answer/korean_policy_template_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_policy_template_routing_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-routing-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-template-total", type=int, default=1000000)
    parser.add_argument("--max-wrong-template-total", type=int, default=1000000)
    parser.add_argument("--max-missing-slot-injection-total", type=int, default=1000000)
    parser.add_argument("--max-non-korean-template-total", type=int, default=1000000)
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
    summary = summarize_korean_policy_template_routing_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_routing_coverage_ratio=max(0.0, float(args.min_routing_coverage_ratio)),
        max_missing_template_total=max(0, int(args.max_missing_template_total)),
        max_wrong_template_total=max(0, int(args.max_wrong_template_total)),
        max_missing_slot_injection_total=max(0, int(args.max_missing_slot_injection_total)),
        max_non_korean_template_total=max(0, int(args.max_non_korean_template_total)),
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
                "min_routing_coverage_ratio": float(args.min_routing_coverage_ratio),
                "max_missing_template_total": int(args.max_missing_template_total),
                "max_wrong_template_total": int(args.max_wrong_template_total),
                "max_missing_slot_injection_total": int(args.max_missing_slot_injection_total),
                "max_non_korean_template_total": int(args.max_non_korean_template_total),
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
    print(f"event_total={_safe_int(summary.get('event_total'), 0)}")
    print(f"routing_coverage_ratio={_safe_float(summary.get('routing_coverage_ratio'), 0.0):.4f}")
    print(f"missing_template_total={_safe_int(summary.get('missing_template_total'), 0)}")
    print(f"missing_slot_injection_total={_safe_int(summary.get('missing_slot_injection_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
