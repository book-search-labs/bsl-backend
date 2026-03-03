#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


LANG_KO = {"KO", "KOR", "KR", "KOREAN", "한국어"}
KEYWORD_EQUIV: dict[str, set[str]] = {
    "order": {"order", "orders", "주문", "주문상태"},
    "refund": {"refund", "refunding", "환불"},
    "shipping": {"shipping", "delivery", "배송", "출고"},
    "cancel": {"cancel", "cancellation", "취소"},
    "policy": {"policy", "policies", "정책", "약관"},
}


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


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


def _source_lang(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("source_lang") or row.get("detected_lang") or row.get("input_lang"))


def _target_lang(row: Mapping[str, Any]) -> str:
    return _normalize_token(row.get("target_lang") or row.get("pivot_lang") or "KO")


def _bridge_required(row: Mapping[str, Any]) -> bool:
    if "bridge_required" in row:
        return _safe_bool(row.get("bridge_required"), False)
    source = _source_lang(row)
    target = _target_lang(row)
    if source and target and source != target:
        return True
    if source and source not in LANG_KO and target in LANG_KO:
        return True
    return False


def _bridge_applied(row: Mapping[str, Any]) -> bool:
    if "bridge_applied" in row:
        return _safe_bool(row.get("bridge_applied"), False)
    return bool(str(row.get("pivot_query") or row.get("rewritten_query") or "").strip())


def _parallel_retrieval_enabled(row: Mapping[str, Any]) -> bool:
    if "parallel_retrieval_enabled" in row:
        return _safe_bool(row.get("parallel_retrieval_enabled"), False)
    if "parallel_retrieval" in row:
        return _safe_bool(row.get("parallel_retrieval"), False)
    return False


def _rewrite_confidence(row: Mapping[str, Any]) -> float:
    for key in ("rewrite_confidence", "bridge_confidence", "translation_confidence"):
        if key in row:
            return max(0.0, min(1.0, _safe_float(row.get(key), 0.0)))
    return 1.0


def _keyword_group_hits(text: str, keyword_groups: dict[str, set[str]]) -> set[str]:
    hits: set[str] = set()
    normalized = _normalize_text(text)
    if not normalized:
        return hits
    for group, aliases in keyword_groups.items():
        for alias in aliases:
            token = _normalize_text(alias)
            if token and token in normalized:
                hits.add(group)
                break
    return hits


def summarize_crosslingual_query_bridge_guard(
    rows: list[Mapping[str, Any]],
    *,
    low_confidence_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    query_total = 0
    bridge_required_total = 0
    bridge_applied_total = 0
    parallel_retrieval_total = 0
    low_confidence_bridge_total = 0
    keyword_required_total = 0
    keyword_preserved_total = 0
    lang_pair_counts: dict[str, int] = {}

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        source = _source_lang(row) or "UNKNOWN"
        target = _target_lang(row) or "UNKNOWN"
        pair = f"{source}->{target}"
        lang_pair_counts[pair] = lang_pair_counts.get(pair, 0) + 1

        query_total += 1
        required = _bridge_required(row)
        if required:
            bridge_required_total += 1

        applied = _bridge_applied(row)
        if applied:
            bridge_applied_total += 1
        if applied and _parallel_retrieval_enabled(row):
            parallel_retrieval_total += 1
        if applied and _rewrite_confidence(row) < max(0.0, min(1.0, float(low_confidence_threshold))):
            low_confidence_bridge_total += 1

        original_query = str(row.get("query") or row.get("original_query") or "").strip()
        pivot_query = str(row.get("pivot_query") or row.get("rewritten_query") or "").strip()
        if not original_query or not pivot_query:
            continue
        original_groups = _keyword_group_hits(original_query, KEYWORD_EQUIV)
        if not original_groups:
            continue
        keyword_required_total += 1
        pivot_groups = _keyword_group_hits(pivot_query, KEYWORD_EQUIV)
        if original_groups.issubset(pivot_groups):
            keyword_preserved_total += 1

    bridge_applied_ratio = 1.0 if bridge_required_total == 0 else float(bridge_applied_total) / float(bridge_required_total)
    parallel_retrieval_coverage_ratio = (
        1.0 if bridge_applied_total == 0 else float(parallel_retrieval_total) / float(bridge_applied_total)
    )
    keyword_preservation_ratio = (
        1.0 if keyword_required_total == 0 else float(keyword_preserved_total) / float(keyword_required_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "query_total": query_total,
        "bridge_required_total": bridge_required_total,
        "bridge_applied_total": bridge_applied_total,
        "bridge_applied_ratio": bridge_applied_ratio,
        "parallel_retrieval_total": parallel_retrieval_total,
        "parallel_retrieval_coverage_ratio": parallel_retrieval_coverage_ratio,
        "low_confidence_bridge_total": low_confidence_bridge_total,
        "keyword_required_total": keyword_required_total,
        "keyword_preserved_total": keyword_preserved_total,
        "keyword_preservation_ratio": keyword_preservation_ratio,
        "lang_pair_distribution": [{"lang_pair": key, "count": value} for key, value in sorted(lang_pair_counts.items())],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_query_total: int,
    min_bridge_applied_ratio: float,
    min_parallel_retrieval_coverage_ratio: float,
    min_keyword_preservation_ratio: float,
    max_low_confidence_bridge_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    query_total = _safe_int(summary.get("query_total"), 0)
    bridge_applied_ratio = _safe_float(summary.get("bridge_applied_ratio"), 0.0)
    parallel_ratio = _safe_float(summary.get("parallel_retrieval_coverage_ratio"), 0.0)
    keyword_ratio = _safe_float(summary.get("keyword_preservation_ratio"), 0.0)
    low_confidence_bridge_total = _safe_int(summary.get("low_confidence_bridge_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"crosslingual bridge window too small: {window_size} < {int(min_window)}")
    if query_total < max(0, int(min_query_total)):
        failures.append(f"crosslingual bridge query total too small: {query_total} < {int(min_query_total)}")
    if window_size == 0:
        return failures

    if bridge_applied_ratio < max(0.0, float(min_bridge_applied_ratio)):
        failures.append(
            f"crosslingual bridge applied ratio below minimum: {bridge_applied_ratio:.4f} < {float(min_bridge_applied_ratio):.4f}"
        )
    if parallel_ratio < max(0.0, float(min_parallel_retrieval_coverage_ratio)):
        failures.append(
            "crosslingual bridge parallel retrieval coverage ratio below minimum: "
            f"{parallel_ratio:.4f} < {float(min_parallel_retrieval_coverage_ratio):.4f}"
        )
    if keyword_ratio < max(0.0, float(min_keyword_preservation_ratio)):
        failures.append(
            f"crosslingual bridge keyword preservation ratio below minimum: {keyword_ratio:.4f} < {float(min_keyword_preservation_ratio):.4f}"
        )
    if low_confidence_bridge_total > max(0, int(max_low_confidence_bridge_total)):
        failures.append(
            "crosslingual bridge low-confidence rewrite total exceeded: "
            f"{low_confidence_bridge_total} > {int(max_low_confidence_bridge_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"crosslingual bridge stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Cross-lingual Query Bridge Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- query_total: {_safe_int(summary.get('query_total'), 0)}")
    lines.append(f"- bridge_applied_ratio: {_safe_float(summary.get('bridge_applied_ratio'), 0.0):.4f}")
    lines.append(
        f"- parallel_retrieval_coverage_ratio: {_safe_float(summary.get('parallel_retrieval_coverage_ratio'), 0.0):.4f}"
    )
    lines.append(f"- keyword_preservation_ratio: {_safe_float(summary.get('keyword_preservation_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate cross-lingual query bridge quality with Korean-priority pivoting.")
    parser.add_argument("--events-jsonl", default="var/crosslingual/query_bridge_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_crosslingual_query_bridge_guard")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.6)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-query-total", type=int, default=0)
    parser.add_argument("--min-bridge-applied-ratio", type=float, default=0.0)
    parser.add_argument("--min-parallel-retrieval-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-keyword-preservation-ratio", type=float, default=0.0)
    parser.add_argument("--max-low-confidence-bridge-total", type=int, default=1000000)
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
    summary = summarize_crosslingual_query_bridge_guard(
        rows,
        low_confidence_threshold=max(0.0, min(1.0, float(args.low_confidence_threshold))),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_query_total=max(0, int(args.min_query_total)),
        min_bridge_applied_ratio=max(0.0, float(args.min_bridge_applied_ratio)),
        min_parallel_retrieval_coverage_ratio=max(0.0, float(args.min_parallel_retrieval_coverage_ratio)),
        min_keyword_preservation_ratio=max(0.0, float(args.min_keyword_preservation_ratio)),
        max_low_confidence_bridge_total=max(0, int(args.max_low_confidence_bridge_total)),
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
                "low_confidence_threshold": float(args.low_confidence_threshold),
                "min_window": int(args.min_window),
                "min_query_total": int(args.min_query_total),
                "min_bridge_applied_ratio": float(args.min_bridge_applied_ratio),
                "min_parallel_retrieval_coverage_ratio": float(args.min_parallel_retrieval_coverage_ratio),
                "min_keyword_preservation_ratio": float(args.min_keyword_preservation_ratio),
                "max_low_confidence_bridge_total": int(args.max_low_confidence_bridge_total),
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
    print(f"bridge_applied_ratio={_safe_float(summary.get('bridge_applied_ratio'), 0.0):.4f}")
    print(
        "parallel_retrieval_coverage_ratio="
        f"{_safe_float(summary.get('parallel_retrieval_coverage_ratio'), 0.0):.4f}"
    )
    print(f"keyword_preservation_ratio={_safe_float(summary.get('keyword_preservation_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
