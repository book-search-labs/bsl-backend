import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def summarize_feedback(records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, int]]:
    counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for item in records:
        rating = str(item.get("rating") or "unknown").strip().lower()
        counts[f"rating_{rating}"] += 1
        if item.get("flag_hallucination"):
            counts["hallucination"] += 1
        if item.get("flag_insufficient"):
            counts["insufficient"] += 1
        if rating == "down":
            reason = str(item.get("reason_code") or "unknown").strip().lower() or "unknown"
            reason_counts[reason] += 1

    total = len(records)
    down = counts.get("rating_down", 0)
    summary = {
        "total": total,
        "rating_up": counts.get("rating_up", 0),
        "rating_down": down,
        "hallucination": counts.get("hallucination", 0),
        "insufficient": counts.get("insufficient", 0),
        "down_rate": (down / total) if total > 0 else 0.0,
        "hallucination_rate": counts.get("hallucination", 0) / total if total > 0 else 0.0,
        "insufficient_rate": counts.get("insufficient", 0) / total if total > 0 else 0.0,
    }
    return summary, dict(reason_counts)


def build_empty_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "rating_up": 0,
        "rating_down": 0,
        "hallucination": 0,
        "insufficient": 0,
        "down_rate": 0.0,
        "hallucination_rate": 0.0,
        "insufficient_rate": 0.0,
        "reason_counts": {},
    }


def build_backlog_items(
    summary: dict[str, Any],
    reason_counts: dict[str, int],
    *,
    min_total_for_backlog: int,
    down_rate_threshold: float,
    hallucination_rate_threshold: float,
    insufficient_rate_threshold: float,
    top_reason_count_threshold: int,
) -> list[dict[str, Any]]:
    total = int(summary.get("total") or 0)
    items: list[dict[str, Any]] = []
    if total < max(1, min_total_for_backlog):
        return items

    down_rate = float(summary.get("down_rate") or 0.0)
    hallucination_rate = float(summary.get("hallucination_rate") or 0.0)
    insufficient_rate = float(summary.get("insufficient_rate") or 0.0)
    if down_rate >= down_rate_threshold:
        items.append(
            {
                "id": "chat.feedback.down_rate",
                "priority": "high",
                "title": "High chat dislike rate",
                "metric": "down_rate",
                "value": down_rate,
                "threshold": down_rate_threshold,
                "suggested_ticket": "B-0627",
                "owner": "chat-recommend",
            }
        )
    if hallucination_rate >= hallucination_rate_threshold:
        items.append(
            {
                "id": "chat.feedback.hallucination_rate",
                "priority": "high",
                "title": "Hallucination flag rate above threshold",
                "metric": "hallucination_rate",
                "value": hallucination_rate,
                "threshold": hallucination_rate_threshold,
                "suggested_ticket": "B-0383",
                "owner": "chat-grounding",
            }
        )
    if insufficient_rate >= insufficient_rate_threshold:
        items.append(
            {
                "id": "chat.feedback.insufficient_rate",
                "priority": "medium",
                "title": "Insufficient-evidence feedback rate above threshold",
                "metric": "insufficient_rate",
                "value": insufficient_rate,
                "threshold": insufficient_rate_threshold,
                "suggested_ticket": "B-0358",
                "owner": "chat-retrieval",
            }
        )
    sorted_reasons = sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)
    for reason, count in sorted_reasons:
        if count < max(1, top_reason_count_threshold):
            continue
        items.append(
            {
                "id": f"chat.feedback.reason.{reason}",
                "priority": "medium",
                "title": f"Top dislike reason: {reason}",
                "metric": "reason_count",
                "value": int(count),
                "threshold": max(1, top_reason_count_threshold),
                "suggested_ticket": "B-0627",
                "owner": "chat-feedback-loop",
            }
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate chat feedback signals.")
    parser.add_argument("--input", default="evaluation/chat/feedback.jsonl")
    parser.add_argument("--output", default="evaluation/chat/feedback_summary.json")
    parser.add_argument("--backlog-output", default="evaluation/chat/feedback_backlog.json")
    parser.add_argument("--min-total-for-backlog", type=int, default=20)
    parser.add_argument("--down-rate-threshold", type=float, default=0.35)
    parser.add_argument("--hallucination-rate-threshold", type=float, default=0.12)
    parser.add_argument("--insufficient-rate-threshold", type=float, default=0.2)
    parser.add_argument("--top-reason-count-threshold", type=int, default=5)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    records = load_jsonl(Path(args.input))
    if not records and not args.allow_empty:
        print("[FAIL] no feedback records")
        return 1

    if records:
        summary, reason_counts = summarize_feedback(records)
        summary["reason_counts"] = reason_counts
    else:
        reason_counts = {}
        summary = build_empty_summary()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"[OK] wrote summary -> {output_path}")

    if str(args.backlog_output or "").strip():
        backlog_items = build_backlog_items(
            summary,
            reason_counts,
            min_total_for_backlog=max(1, int(args.min_total_for_backlog)),
            down_rate_threshold=max(0.0, min(1.0, float(args.down_rate_threshold))),
            hallucination_rate_threshold=max(0.0, min(1.0, float(args.hallucination_rate_threshold))),
            insufficient_rate_threshold=max(0.0, min(1.0, float(args.insufficient_rate_threshold))),
            top_reason_count_threshold=max(1, int(args.top_reason_count_threshold)),
        )
        backlog_payload: Dict[str, Any] = {
            "version": "v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": str(args.input),
            "total": summary.get("total", 0),
            "thresholds": {
                "min_total_for_backlog": max(1, int(args.min_total_for_backlog)),
                "down_rate_threshold": max(0.0, min(1.0, float(args.down_rate_threshold))),
                "hallucination_rate_threshold": max(0.0, min(1.0, float(args.hallucination_rate_threshold))),
                "insufficient_rate_threshold": max(0.0, min(1.0, float(args.insufficient_rate_threshold))),
                "top_reason_count_threshold": max(1, int(args.top_reason_count_threshold)),
            },
            "items": backlog_items,
        }
        backlog_path = Path(args.backlog_output)
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        backlog_path.write_text(json.dumps(backlog_payload, ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"[OK] wrote backlog -> {backlog_path}")

    if not records and args.allow_empty:
        print("[OK] no feedback records; emitted empty summary/backlog payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
