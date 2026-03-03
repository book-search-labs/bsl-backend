#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


LANG_KO = {"KO", "KOR", "KR", "KOREAN", "한국어"}


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


def _is_ko(lang: str) -> bool:
    return _normalize_token(lang) in LANG_KO


def summarize_korean_priority_ranking_guard(
    rows: list[Mapping[str, Any]],
    *,
    top_k: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        query_id = str(row.get("query_id") or row.get("request_id") or row.get("trace_id") or "").strip()
        if not query_id:
            continue
        grouped.setdefault(query_id, []).append({str(k): v for k, v in row.items()})

    query_total = 0
    korean_candidate_query_total = 0
    korean_top1_total = 0
    korean_topk_covered_total = 0
    non_korean_top1_when_korean_available_total = 0
    priority_boost_applied_total = 0
    query_rows: list[dict[str, Any]] = []

    for query_id, items in sorted(grouped.items(), key=lambda item: item[0]):
        ranked = sorted(items, key=lambda row: _safe_int(row.get("rank"), 999999))
        if not ranked:
            continue
        query_total += 1

        has_korean_candidate = any(_is_ko(str(row.get("doc_lang") or row.get("language") or row.get("result_lang"))) for row in ranked)
        top1_lang = _normalize_token(ranked[0].get("doc_lang") or ranked[0].get("language") or ranked[0].get("result_lang"))
        topk_slice = ranked[: max(1, int(top_k))]
        topk_has_ko = any(_is_ko(str(row.get("doc_lang") or row.get("language") or row.get("result_lang"))) for row in topk_slice)
        boost_applied = any(
            _safe_bool(
                row.get("korean_priority_boost_applied")
                or row.get("ko_priority_boost_applied")
                or row.get("korean_boost_applied"),
                False,
            )
            for row in ranked
        )

        if has_korean_candidate:
            korean_candidate_query_total += 1
            if _is_ko(top1_lang):
                korean_top1_total += 1
            else:
                non_korean_top1_when_korean_available_total += 1
            if topk_has_ko:
                korean_topk_covered_total += 1
            if boost_applied:
                priority_boost_applied_total += 1

        query_rows.append(
            {
                "query_id": query_id,
                "has_korean_candidate": has_korean_candidate,
                "top1_lang": top1_lang,
                "topk_has_ko": topk_has_ko,
                "boost_applied": boost_applied,
            }
        )

    korean_top1_ratio = (
        1.0 if korean_candidate_query_total == 0 else float(korean_top1_total) / float(korean_candidate_query_total)
    )
    korean_topk_coverage_ratio = (
        1.0 if korean_candidate_query_total == 0 else float(korean_topk_covered_total) / float(korean_candidate_query_total)
    )
    priority_boost_applied_ratio = (
        1.0 if korean_candidate_query_total == 0 else float(priority_boost_applied_total) / float(korean_candidate_query_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "query_total": query_total,
        "korean_candidate_query_total": korean_candidate_query_total,
        "korean_top1_total": korean_top1_total,
        "korean_top1_ratio": korean_top1_ratio,
        "korean_topk_covered_total": korean_topk_covered_total,
        "korean_topk_coverage_ratio": korean_topk_coverage_ratio,
        "priority_boost_applied_total": priority_boost_applied_total,
        "priority_boost_applied_ratio": priority_boost_applied_ratio,
        "non_korean_top1_when_korean_available_total": non_korean_top1_when_korean_available_total,
        "queries": query_rows,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_query_total: int,
    min_korean_top1_ratio: float,
    min_korean_topk_coverage_ratio: float,
    min_priority_boost_applied_ratio: float,
    max_non_korean_top1_when_korean_available_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    query_total = _safe_int(summary.get("query_total"), 0)
    korean_top1_ratio = _safe_float(summary.get("korean_top1_ratio"), 0.0)
    korean_topk_coverage_ratio = _safe_float(summary.get("korean_topk_coverage_ratio"), 0.0)
    priority_boost_applied_ratio = _safe_float(summary.get("priority_boost_applied_ratio"), 0.0)
    non_korean_top1_when_korean_available_total = _safe_int(summary.get("non_korean_top1_when_korean_available_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"korean priority ranking window too small: {window_size} < {int(min_window)}")
    if query_total < max(0, int(min_query_total)):
        failures.append(f"korean priority ranking query total too small: {query_total} < {int(min_query_total)}")
    if window_size == 0:
        return failures

    if korean_top1_ratio < max(0.0, float(min_korean_top1_ratio)):
        failures.append(
            f"korean priority ranking top1 ratio below minimum: {korean_top1_ratio:.4f} < {float(min_korean_top1_ratio):.4f}"
        )
    if korean_topk_coverage_ratio < max(0.0, float(min_korean_topk_coverage_ratio)):
        failures.append(
            "korean priority ranking top-k coverage ratio below minimum: "
            f"{korean_topk_coverage_ratio:.4f} < {float(min_korean_topk_coverage_ratio):.4f}"
        )
    if priority_boost_applied_ratio < max(0.0, float(min_priority_boost_applied_ratio)):
        failures.append(
            "korean priority ranking boost-applied ratio below minimum: "
            f"{priority_boost_applied_ratio:.4f} < {float(min_priority_boost_applied_ratio):.4f}"
        )
    if non_korean_top1_when_korean_available_total > max(0, int(max_non_korean_top1_when_korean_available_total)):
        failures.append(
            "korean priority ranking non-korean top1 with korean candidate total exceeded: "
            f"{non_korean_top1_when_korean_available_total} > {int(max_non_korean_top1_when_korean_available_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"korean priority ranking stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Priority Ranking Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- query_total: {_safe_int(summary.get('query_total'), 0)}")
    lines.append(f"- korean_top1_ratio: {_safe_float(summary.get('korean_top1_ratio'), 0.0):.4f}")
    lines.append(f"- korean_topk_coverage_ratio: {_safe_float(summary.get('korean_topk_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- priority_boost_applied_ratio: {_safe_float(summary.get('priority_boost_applied_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate Korean-priority ranking outcomes for cross-lingual retrieval.")
    parser.add_argument("--events-jsonl", default="var/crosslingual/korean_priority_ranking_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_priority_ranking_guard")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-query-total", type=int, default=0)
    parser.add_argument("--min-korean-top1-ratio", type=float, default=0.0)
    parser.add_argument("--min-korean-topk-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-priority-boost-applied-ratio", type=float, default=0.0)
    parser.add_argument("--max-non-korean-top1-when-korean-available-total", type=int, default=1000000)
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
    summary = summarize_korean_priority_ranking_guard(
        rows,
        top_k=max(1, int(args.top_k)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_query_total=max(0, int(args.min_query_total)),
        min_korean_top1_ratio=max(0.0, float(args.min_korean_top1_ratio)),
        min_korean_topk_coverage_ratio=max(0.0, float(args.min_korean_topk_coverage_ratio)),
        min_priority_boost_applied_ratio=max(0.0, float(args.min_priority_boost_applied_ratio)),
        max_non_korean_top1_when_korean_available_total=max(
            0, int(args.max_non_korean_top1_when_korean_available_total)
        ),
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
                "top_k": int(args.top_k),
                "min_window": int(args.min_window),
                "min_query_total": int(args.min_query_total),
                "min_korean_top1_ratio": float(args.min_korean_top1_ratio),
                "min_korean_topk_coverage_ratio": float(args.min_korean_topk_coverage_ratio),
                "min_priority_boost_applied_ratio": float(args.min_priority_boost_applied_ratio),
                "max_non_korean_top1_when_korean_available_total": int(
                    args.max_non_korean_top1_when_korean_available_total
                ),
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
    print(f"korean_top1_ratio={_safe_float(summary.get('korean_top1_ratio'), 0.0):.4f}")
    print(f"korean_topk_coverage_ratio={_safe_float(summary.get('korean_topk_coverage_ratio'), 0.0):.4f}")
    print(f"priority_boost_applied_ratio={_safe_float(summary.get('priority_boost_applied_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
