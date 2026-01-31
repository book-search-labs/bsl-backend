import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def load_queries(path: Path) -> dict:
    queries = {}
    for item in load_jsonl(path):
        query_id = item.get("query_id") or item.get("id")
        if not query_id:
            continue
        queries[str(query_id)] = {
            "query": item.get("query") or item.get("text") or "",
            "set": item.get("set") or "golden",
        }
    return queries


def load_judgments(path: Path) -> dict:
    judgments = defaultdict(dict)
    for item in load_jsonl(path):
        query_id = item.get("query_id") or item.get("qid")
        doc_id = item.get("doc_id") or item.get("doc")
        if not query_id or not doc_id:
            continue
        grade = item.get("grade")
        if grade is None:
            grade = item.get("label")
        if grade is None:
            grade = item.get("relevance", 0)
        try:
            grade_value = float(grade)
        except Exception:
            grade_value = 0.0
        judgments[str(query_id)][str(doc_id)] = grade_value
    return judgments


def load_run(path: Path) -> dict:
    runs = defaultdict(list)
    for item in load_jsonl(path):
        query_id = item.get("query_id") or item.get("qid")
        doc_id = item.get("doc_id") or item.get("doc")
        if not query_id or not doc_id:
            continue
        entry = {
            "doc_id": str(doc_id),
            "score": item.get("score"),
            "rank": item.get("rank"),
        }
        runs[str(query_id)].append(entry)
    return runs


def sort_run(entries: list[dict]) -> list[dict]:
    if not entries:
        return []
    if any(entry.get("rank") is not None for entry in entries):
        return sorted(entries, key=lambda e: (e.get("rank") or 10**9))
    return sorted(entries, key=lambda e: (e.get("score") or 0.0), reverse=True)


def dcg(rels: list[float]) -> float:
    score = 0.0
    for idx, rel in enumerate(rels):
        score += (2.0 ** rel - 1.0) / math.log2(idx + 2.0)
    return score


def ndcg_at_k(rels: list[float], k: int) -> float:
    if not rels:
        return 0.0
    rels = rels[:k]
    ideal = sorted(rels, reverse=True)
    denom = dcg(ideal)
    if denom <= 0:
        return 0.0
    return dcg(rels) / denom


def mrr_at_k(rels: list[float], k: int) -> float:
    for idx, rel in enumerate(rels[:k]):
        if rel > 0:
            return 1.0 / (idx + 1)
    return 0.0


def recall_at_k(rels: list[float], total_rels: int, k: int) -> float:
    if total_rels <= 0:
        return 0.0
    hit = sum(1 for rel in rels[:k] if rel > 0)
    return hit / float(total_rels)


def compute_metrics(query_ids: list[str], runs: dict, judgments: dict) -> dict:
    ndcg_values = []
    mrr_values = []
    recall_values = []
    zero_results = 0
    latency_proxy = []

    for qid in query_ids:
        ranked = sort_run(runs.get(qid, []))
        latency_proxy.append(len(ranked))
        if not ranked:
            zero_results += 1
        judged = judgments.get(qid, {})
        rels = [judged.get(entry["doc_id"], 0.0) for entry in ranked]
        total_rels = sum(1 for value in judged.values() if value > 0)
        ndcg_values.append(ndcg_at_k(rels, 10))
        mrr_values.append(mrr_at_k(rels, 10))
        recall_values.append(recall_at_k(rels, total_rels, 100))

    count = max(len(query_ids), 1)
    return {
        "ndcg_10": sum(ndcg_values) / count,
        "mrr_10": sum(mrr_values) / count,
        "recall_100": sum(recall_values) / count,
        "zero_result_rate": zero_results / count,
        "latency_proxy": sum(latency_proxy) / count,
        "query_count": len(query_ids),
    }


def build_report(queries: dict, runs: dict, judgments: dict, sets: list[str]) -> dict:
    if not sets:
        sets = sorted({meta["set"] for meta in queries.values()})
    report_sets = {}
    overall_ids: list[str] = []
    for set_name in sets:
        ids = [qid for qid, meta in queries.items() if meta.get("set") == set_name]
        if not ids:
            continue
        report_sets[set_name] = compute_metrics(ids, runs, judgments)
        overall_ids.extend(ids)

    overall_metrics = compute_metrics(overall_ids, runs, judgments) if overall_ids else {}
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": "v1",
        "run_id": f"eval_{now}",
        "generated_at": now,
        "sets": report_sets,
        "overall": overall_metrics,
    }


def load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_reports(baseline: dict, candidate: dict, max_drop: float, max_zero_increase: float, max_latency_increase: float) -> list[str]:
    errors: list[str] = []
    quality_keys = ["ndcg_10", "mrr_10", "recall_100"]

    def compare_set(name: str, base: dict, cand: dict) -> None:
        for key in quality_keys:
            base_val = base.get(key)
            cand_val = cand.get(key)
            if base_val is None or cand_val is None:
                continue
            if cand_val < base_val - max_drop:
                errors.append(f"{name}:{key} dropped {base_val:.4f} -> {cand_val:.4f}")
        base_zero = base.get("zero_result_rate")
        cand_zero = cand.get("zero_result_rate")
        if base_zero is not None and cand_zero is not None:
            if cand_zero > base_zero + max_zero_increase:
                errors.append(f"{name}:zero_result_rate increased {base_zero:.4f} -> {cand_zero:.4f}")
        base_latency = base.get("latency_proxy")
        cand_latency = cand.get("latency_proxy")
        if base_latency is not None and cand_latency is not None and base_latency > 0:
            if cand_latency > base_latency * (1.0 + max_latency_increase):
                errors.append(
                    f"{name}:latency_proxy increased {base_latency:.2f} -> {cand_latency:.2f}"
                )

    compare_set("overall", baseline.get("overall", {}), candidate.get("overall", {}))
    base_sets = baseline.get("sets", {})
    cand_sets = candidate.get("sets", {})
    for set_name, base_metrics in base_sets.items():
        if set_name in cand_sets:
            compare_set(set_name, base_metrics, cand_sets[set_name])
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline eval runner with regression gate.")
    parser.add_argument("--queries", default="evaluation/queries.jsonl")
    parser.add_argument("--judgments", default="evaluation/judgments.jsonl")
    parser.add_argument("--run", default="evaluation/runs/sample_run.jsonl")
    parser.add_argument("--sets", default="")
    parser.add_argument("--output", default="evaluation/eval_runs/latest.json")
    parser.add_argument("--write-baseline", default="")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--max-drop", type=float, default=0.02)
    parser.add_argument("--max-zero-increase", type=float, default=0.02)
    parser.add_argument("--max-latency-increase", type=float, default=0.2)
    args = parser.parse_args()

    queries = load_queries(Path(args.queries))
    if not queries:
        print("[FAIL] no queries loaded")
        return 1
    judgments = load_judgments(Path(args.judgments))
    runs = load_run(Path(args.run))
    if not runs:
        print("[FAIL] no run data loaded")
        return 1

    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    report = build_report(queries, runs, judgments, sets)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
    print(f"[OK] wrote eval report -> {output_path}")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with baseline_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=True, indent=2)
        print(f"[OK] wrote baseline -> {baseline_path}")

    if args.baseline:
        baseline = load_report(Path(args.baseline))
        errors = compare_reports(
            baseline,
            report,
            max_drop=args.max_drop,
            max_zero_increase=args.max_zero_increase,
            max_latency_increase=args.max_latency_increase,
        )
        if errors:
            print("[FAIL] regression detected:")
            for error in errors:
                print(" -", error)
            return 2 if args.gate else 0
        print("[OK] eval gate passed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
