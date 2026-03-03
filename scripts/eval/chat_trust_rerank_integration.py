#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE_TRUST_DEFAULTS = {
    "OFFICIAL_POLICY": 1.00,
    "EVENT_NOTICE": 0.80,
    "ANNOUNCEMENT": 0.70,
    "USER_GENERATED": 0.30,
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
    for key in ("timestamp", "event_time", "updated_at", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_source_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "POLICY": "OFFICIAL_POLICY",
        "EVENT": "EVENT_NOTICE",
        "NOTICE": "ANNOUNCEMENT",
        "UGC": "USER_GENERATED",
    }
    if text in SOURCE_TRUST_DEFAULTS:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _query_id(row: Mapping[str, Any]) -> str:
    for key in ("query_id", "request_id", "conversation_id", "trace_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _base_score(row: Mapping[str, Any]) -> float:
    for key in ("retrieval_score", "score", "base_score", "rank_score"):
        if key in row:
            return _safe_float(row.get(key), 0.0)
    return 0.0


def _trust_weight(row: Mapping[str, Any]) -> float:
    explicit = row.get("trust_weight")
    if explicit is not None:
        return max(0.0, min(1.0, _safe_float(explicit, 0.0)))
    source_type = _normalize_source_type(row.get("source_type") or row.get("type"))
    return float(SOURCE_TRUST_DEFAULTS.get(source_type, 0.5))


def _freshness_ttl_sec(row: Mapping[str, Any], *, default_ttl_sec: float) -> float:
    ttl = row.get("freshness_ttl_sec")
    if ttl is None:
        ttl = row.get("freshness_ttl")
    ttl_value = _safe_float(ttl, default_ttl_sec)
    return max(1.0, ttl_value)


def _is_stale(row: Mapping[str, Any], *, now: datetime, default_ttl_sec: float) -> bool:
    ts = _event_ts(row)
    if ts is None:
        return False
    ttl_sec = _freshness_ttl_sec(row, default_ttl_sec=default_ttl_sec)
    age_sec = max(0.0, (now - ts).total_seconds())
    return age_sec > ttl_sec


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


def summarize_trust_rerank(
    events: list[Mapping[str, Any]],
    *,
    top_k: int,
    low_trust_threshold: float,
    trust_boost_scale: float,
    stale_penalty: float,
    default_freshness_ttl_sec: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    latest_ts: datetime | None = None

    for row in events:
        qid = _query_id(row)
        if not qid:
            continue
        grouped.setdefault(qid, []).append(row)
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    query_total = len(grouped)
    candidate_total = sum(len(items) for items in grouped.values())

    low_trust_before_total = 0
    low_trust_after_total = 0
    stale_before_total = 0
    stale_after_total = 0
    topk_slot_total = 0
    rerank_shift_query_total = 0

    for docs in grouped.values():
        baseline = sorted(docs, key=_base_score, reverse=True)
        reranked = sorted(
            docs,
            key=lambda item: _base_score(item)
            + (_trust_weight(item) * float(trust_boost_scale))
            - (float(stale_penalty) if _is_stale(item, now=now_dt, default_ttl_sec=default_freshness_ttl_sec) else 0.0),
            reverse=True,
        )

        k = min(max(1, int(top_k)), len(docs))
        topk_slot_total += k
        top_before = baseline[:k]
        top_after = reranked[:k]
        if [id(item) for item in top_before] != [id(item) for item in top_after]:
            rerank_shift_query_total += 1

        for item in top_before:
            if _trust_weight(item) < float(low_trust_threshold):
                low_trust_before_total += 1
            if _is_stale(item, now=now_dt, default_ttl_sec=default_freshness_ttl_sec):
                stale_before_total += 1
        for item in top_after:
            if _trust_weight(item) < float(low_trust_threshold):
                low_trust_after_total += 1
            if _is_stale(item, now=now_dt, default_ttl_sec=default_freshness_ttl_sec):
                stale_after_total += 1

    low_trust_before_ratio = 0.0 if topk_slot_total == 0 else float(low_trust_before_total) / float(topk_slot_total)
    low_trust_after_ratio = 0.0 if topk_slot_total == 0 else float(low_trust_after_total) / float(topk_slot_total)
    stale_before_ratio = 0.0 if topk_slot_total == 0 else float(stale_before_total) / float(topk_slot_total)
    stale_after_ratio = 0.0 if topk_slot_total == 0 else float(stale_after_total) / float(topk_slot_total)

    if low_trust_before_ratio <= 0.0:
        trust_lift_ratio = 1.0 if low_trust_after_ratio <= 0.0 else 0.0
    else:
        trust_lift_ratio = max(0.0, (low_trust_before_ratio - low_trust_after_ratio) / low_trust_before_ratio)
    if stale_before_ratio <= 0.0:
        stale_drop_ratio = 1.0 if stale_after_ratio <= 0.0 else 0.0
    else:
        stale_drop_ratio = max(0.0, (stale_before_ratio - stale_after_ratio) / stale_before_ratio)

    rerank_shift_ratio = 0.0 if query_total == 0 else float(rerank_shift_query_total) / float(query_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "query_total": query_total,
        "candidate_total": candidate_total,
        "topk_slot_total": topk_slot_total,
        "low_trust_topk_before_total": low_trust_before_total,
        "low_trust_topk_after_total": low_trust_after_total,
        "low_trust_topk_before_ratio": low_trust_before_ratio,
        "low_trust_topk_after_ratio": low_trust_after_ratio,
        "stale_topk_before_total": stale_before_total,
        "stale_topk_after_total": stale_after_total,
        "stale_topk_before_ratio": stale_before_ratio,
        "stale_topk_after_ratio": stale_after_ratio,
        "trust_lift_ratio": trust_lift_ratio,
        "stale_drop_ratio": stale_drop_ratio,
        "rerank_shift_query_total": rerank_shift_query_total,
        "rerank_shift_ratio": rerank_shift_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_query_total: int,
    max_low_trust_topk_ratio: float,
    max_stale_topk_ratio: float,
    min_trust_lift_ratio: float,
    min_stale_drop_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    query_total = _safe_int(summary.get("query_total"), 0)
    low_trust_topk_after_ratio = _safe_float(summary.get("low_trust_topk_after_ratio"), 0.0)
    stale_topk_after_ratio = _safe_float(summary.get("stale_topk_after_ratio"), 0.0)
    trust_lift_ratio = _safe_float(summary.get("trust_lift_ratio"), 0.0)
    stale_drop_ratio = _safe_float(summary.get("stale_drop_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"trust rerank window too small: {window_size} < {int(min_window)}")
    if query_total < max(0, int(min_query_total)):
        failures.append(f"trust rerank query window too small: {query_total} < {int(min_query_total)}")
    if window_size == 0:
        return failures

    if low_trust_topk_after_ratio > max(0.0, float(max_low_trust_topk_ratio)):
        failures.append(
            "low trust source top-k ratio exceeded: "
            f"{low_trust_topk_after_ratio:.4f} > {float(max_low_trust_topk_ratio):.4f}"
        )
    if stale_topk_after_ratio > max(0.0, float(max_stale_topk_ratio)):
        failures.append(
            f"stale source top-k ratio exceeded: {stale_topk_after_ratio:.4f} > {float(max_stale_topk_ratio):.4f}"
        )
    if trust_lift_ratio < max(0.0, float(min_trust_lift_ratio)):
        failures.append(f"trust lift ratio below threshold: {trust_lift_ratio:.4f} < {float(min_trust_lift_ratio):.4f}")
    if stale_drop_ratio < max(0.0, float(min_stale_drop_ratio)):
        failures.append(f"stale drop ratio below threshold: {stale_drop_ratio:.4f} < {float(min_stale_drop_ratio):.4f}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"trust rerank events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Trust Rerank Integration")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- query_total: {_safe_int(summary.get('query_total'), 0)}")
    lines.append(f"- low_trust_topk_before_ratio: {_safe_float(summary.get('low_trust_topk_before_ratio'), 0.0):.4f}")
    lines.append(f"- low_trust_topk_after_ratio: {_safe_float(summary.get('low_trust_topk_after_ratio'), 0.0):.4f}")
    lines.append(f"- stale_topk_before_ratio: {_safe_float(summary.get('stale_topk_before_ratio'), 0.0):.4f}")
    lines.append(f"- stale_topk_after_ratio: {_safe_float(summary.get('stale_topk_after_ratio'), 0.0):.4f}")
    lines.append(f"- trust_lift_ratio: {_safe_float(summary.get('trust_lift_ratio'), 0.0):.4f}")
    lines.append(f"- stale_drop_ratio: {_safe_float(summary.get('stale_drop_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate trust-aware retrieval + rerank integration quality.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/retrieval_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--low-trust-threshold", type=float, default=0.5)
    parser.add_argument("--trust-boost-scale", type=float, default=0.3)
    parser.add_argument("--stale-penalty", type=float, default=0.5)
    parser.add_argument("--default-freshness-ttl-sec", type=float, default=86400)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_trust_rerank_integration")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-query-total", type=int, default=0)
    parser.add_argument("--max-low-trust-topk-ratio", type=float, default=0.40)
    parser.add_argument("--max-stale-topk-ratio", type=float, default=0.20)
    parser.add_argument("--min-trust-lift-ratio", type=float, default=0.0)
    parser.add_argument("--min-stale-drop-ratio", type=float, default=0.0)
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
    summary = summarize_trust_rerank(
        events,
        top_k=max(1, int(args.top_k)),
        low_trust_threshold=max(0.0, min(1.0, float(args.low_trust_threshold))),
        trust_boost_scale=max(0.0, float(args.trust_boost_scale)),
        stale_penalty=max(0.0, float(args.stale_penalty)),
        default_freshness_ttl_sec=max(1.0, float(args.default_freshness_ttl_sec)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_query_total=max(0, int(args.min_query_total)),
        max_low_trust_topk_ratio=max(0.0, float(args.max_low_trust_topk_ratio)),
        max_stale_topk_ratio=max(0.0, float(args.max_stale_topk_ratio)),
        min_trust_lift_ratio=max(0.0, float(args.min_trust_lift_ratio)),
        min_stale_drop_ratio=max(0.0, float(args.min_stale_drop_ratio)),
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
                "min_query_total": int(args.min_query_total),
                "max_low_trust_topk_ratio": float(args.max_low_trust_topk_ratio),
                "max_stale_topk_ratio": float(args.max_stale_topk_ratio),
                "min_trust_lift_ratio": float(args.min_trust_lift_ratio),
                "min_stale_drop_ratio": float(args.min_stale_drop_ratio),
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
    print(f"query_total={_safe_int(summary.get('query_total'), 0)}")
    print(f"low_trust_topk_after_ratio={_safe_float(summary.get('low_trust_topk_after_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
