import argparse
import json
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate chat feedback signals.")
    parser.add_argument("--input", default="evaluation/chat/feedback.jsonl")
    parser.add_argument("--output", default="evaluation/chat/feedback_summary.json")
    args = parser.parse_args()

    records = load_jsonl(Path(args.input))
    if not records:
        print("[FAIL] no feedback records")
        return 1

    counts = Counter()
    for item in records:
        rating = item.get("rating") or "unknown"
        counts[f"rating_{rating}"] += 1
        if item.get("flag_hallucination"):
            counts["hallucination"] += 1
        if item.get("flag_insufficient"):
            counts["insufficient"] += 1

    total = len(records)
    summary = {
        "total": total,
        "rating_up": counts.get("rating_up", 0),
        "rating_down": counts.get("rating_down", 0),
        "hallucination": counts.get("hallucination", 0),
        "insufficient": counts.get("insufficient", 0),
        "hallucination_rate": counts.get("hallucination", 0) / total,
        "insufficient_rate": counts.get("insufficient", 0) / total,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"[OK] wrote summary -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
