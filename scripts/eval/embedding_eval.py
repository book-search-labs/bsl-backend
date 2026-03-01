import argparse
import json
import math
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def load_queries(path: Path) -> List[dict]:
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def toy_embed(text: str, dim: int) -> List[float]:
    import hashlib
    import random

    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()[:8]
    seed = int.from_bytes(seed_bytes, "big", signed=False)
    rng = random.Random(seed)
    values = [rng.random() for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_queries_mis(
    mis_url: str, model: str, texts: List[str], batch_size: int, timeout: float
) -> List[List[float]]:
    vectors: List[List[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        payload = {"model": model, "texts": batch, "normalize": True}
        data = post_json(f"{mis_url.rstrip('/')}/v1/embed", payload, timeout)
        batch_vectors = data.get("vectors") or []
        if len(batch_vectors) != len(batch):
            raise RuntimeError("embedding size mismatch")
        vectors.extend(batch_vectors)
    return vectors


def extract_doc_ids(response: dict) -> List[str]:
    hits = response.get("hits", {}).get("hits", [])
    doc_ids = []
    for hit in hits:
        source = hit.get("_source") or {}
        doc_id = source.get("doc_id") or hit.get("_id")
        if doc_id:
            doc_ids.append(doc_id)
    return doc_ids


def search_vector(os_url: str, index: str, vector: List[float], topk: int, timeout: float) -> List[str]:
    payload = {"size": topk, "query": {"knn": {"embedding": {"vector": vector, "k": topk}}}}
    data = post_json(f"{os_url.rstrip('/')}/{index}/_search", payload, timeout)
    return extract_doc_ids(data)


def search_lexical(os_url: str, index: str, query: str, topk: int, timeout: float) -> List[str]:
    payload = {
        "size": topk,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title_ko", "title_en", "author_names_ko", "series_name", "publisher_name"],
            }
        },
    }
    data = post_json(f"{os_url.rstrip('/')}/{index}/_search", payload, timeout)
    return extract_doc_ids(data)


def rrf_fuse(lex: List[str], vec: List[str], k: int) -> List[str]:
    scores: Dict[str, float] = defaultdict(float)
    for rank, doc_id in enumerate(lex, start=1):
        scores[doc_id] += 1.0 / (k + rank)
    for rank, doc_id in enumerate(vec, start=1):
        scores[doc_id] += 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def dcg(rels: List[int]) -> float:
    score = 0.0
    for idx, rel in enumerate(rels):
        score += (2.0 ** rel - 1.0) / math.log2(idx + 2.0)
    return score


def ndcg_at_k(rels: List[int], k: int) -> float:
    if not rels:
        return 0.0
    rels = rels[:k]
    ideal = sorted(rels, reverse=True)
    denom = dcg(ideal)
    if denom <= 0:
        return 0.0
    return dcg(rels) / denom


def mrr_at_k(rels: List[int], k: int) -> float:
    for idx, rel in enumerate(rels[:k]):
        if rel > 0:
            return 1.0 / (idx + 1)
    return 0.0


def recall_at_k(rels: List[int], total_rels: int, k: int) -> float:
    if total_rels <= 0:
        return 0.0
    hit = sum(1 for rel in rels[:k] if rel > 0)
    return hit / float(total_rels)


def evaluate_runs(queries: List[dict], runs: Dict[str, List[str]]) -> Tuple[dict, List[dict]]:
    ndcg_values = []
    mrr_values = []
    recall_values = []
    zero_results = 0
    cases = []

    for item in queries:
        qid = item.get("qid")
        relevant = set(item.get("relevant_doc_ids") or [])
        ranked = runs.get(qid, [])
        rels = [1 if doc_id in relevant else 0 for doc_id in ranked]
        total_rels = len(relevant)
        if not ranked:
            zero_results += 1
        ndcg = ndcg_at_k(rels, 10)
        mrr = mrr_at_k(rels, 10)
        recall = recall_at_k(rels, total_rels, 50)
        ndcg_values.append(ndcg)
        mrr_values.append(mrr)
        recall_values.append(recall)
        cases.append({"qid": qid, "query": item.get("query"), "ndcg": ndcg, "mrr": mrr, "recall": recall})

    count = max(len(queries), 1)
    metrics = {
        "ndcg_10": sum(ndcg_values) / count,
        "mrr_10": sum(mrr_values) / count,
        "recall_50": sum(recall_values) / count,
        "zero_result_rate": zero_results / count,
        "query_count": len(queries),
    }
    return metrics, cases


def build_report(
    queries: List[dict],
    baseline_runs: Dict[str, List[str]],
    candidate_runs: Dict[str, List[str]],
) -> dict:
    baseline_metrics, baseline_cases = evaluate_runs(queries, baseline_runs)
    candidate_metrics, candidate_cases = evaluate_runs(queries, candidate_runs)

    diff = {
        key: candidate_metrics.get(key, 0.0) - baseline_metrics.get(key, 0.0)
        for key in baseline_metrics.keys()
    }

    improved = []
    regressed = []
    baseline_by_qid = {item["qid"]: item for item in baseline_cases}
    for cand in candidate_cases:
        base = baseline_by_qid.get(cand["qid"], {})
        delta = cand.get("ndcg", 0.0) - base.get("ndcg", 0.0)
        entry = {
            "qid": cand["qid"],
            "query": cand.get("query"),
            "baseline_ndcg": base.get("ndcg", 0.0),
            "candidate_ndcg": cand.get("ndcg", 0.0),
            "delta": delta,
        }
        if delta >= 0:
            improved.append(entry)
        else:
            regressed.append(entry)

    improved = sorted(improved, key=lambda item: item["delta"], reverse=True)[:20]
    regressed = sorted(regressed, key=lambda item: item["delta"])[:20]

    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": "v1",
        "generated_at": now,
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "diff": diff,
        "improved_cases": improved,
        "regressed_cases": regressed,
    }


def render_markdown(report: dict, baseline_name: str, candidate_name: str) -> str:
    lines = []
    lines.append(f"# Embedding Eval Report ({baseline_name} -> {candidate_name})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Baseline | Candidate | Diff |")
    lines.append("| --- | --- | --- | --- |")
    for key in ["ndcg_10", "mrr_10", "recall_50", "zero_result_rate"]:
        base = report["baseline"].get(key, 0.0)
        cand = report["candidate"].get(key, 0.0)
        diff = report["diff"].get(key, 0.0)
        lines.append(f"| {key} | {base:.4f} | {cand:.4f} | {diff:+.4f} |")

    lines.append("")
    lines.append("## Improved cases")
    for item in report.get("improved_cases", []):
        lines.append(f"- {item['qid']}: {item['query']} (\u0394NDCG={item['delta']:+.4f})")

    lines.append("")
    lines.append("## Regressed cases")
    for item in report.get("regressed_cases", []):
        lines.append(f"- {item['qid']}: {item['query']} (\u0394NDCG={item['delta']:+.4f})")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Embedding/Hybrid offline evaluation")
    parser.add_argument("--queries", default="data/eval/embedding_queries.jsonl")
    parser.add_argument("--baseline", default="toy")
    parser.add_argument("--candidate", default="multilingual-e5-small")
    parser.add_argument("--topk", type=int, default=50)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--os-url", default="http://localhost:9200")
    parser.add_argument("--vec-index", default="books_vec_read")
    parser.add_argument("--doc-index", default="books_doc_read")
    parser.add_argument("--mis-url", default="http://localhost:8005")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--toy-dim", type=int, default=384)
    parser.add_argument("--out", default="data/eval/reports")
    args = parser.parse_args()

    queries = load_queries(Path(args.queries))
    if not queries:
        print("[FAIL] no queries found")
        return 1

    query_texts = [item.get("query") or "" for item in queries]

    def build_embeddings(label: str) -> List[List[float]]:
        if label == "toy":
            return [toy_embed(text, args.toy_dim) for text in query_texts]
        return embed_queries_mis(args.mis_url, label, query_texts, args.batch_size, args.timeout)

    baseline_vectors = build_embeddings(args.baseline)
    candidate_vectors = build_embeddings(args.candidate)

    baseline_runs: Dict[str, List[str]] = {}
    candidate_runs: Dict[str, List[str]] = {}
    for item, base_vec, cand_vec in zip(queries, baseline_vectors, candidate_vectors):
        qid = item.get("qid")
        if not qid:
            continue
        if args.hybrid:
            lex = search_lexical(args.os_url, args.doc_index, item.get("query") or "", args.topk, args.timeout)
            base_vec_hits = search_vector(args.os_url, args.vec_index, base_vec, args.topk, args.timeout)
            cand_vec_hits = search_vector(args.os_url, args.vec_index, cand_vec, args.topk, args.timeout)
            baseline_runs[qid] = rrf_fuse(lex, base_vec_hits, args.rrf_k)
            candidate_runs[qid] = rrf_fuse(lex, cand_vec_hits, args.rrf_k)
        else:
            baseline_runs[qid] = search_vector(args.os_url, args.vec_index, base_vec, args.topk, args.timeout)
            candidate_runs[qid] = search_vector(args.os_url, args.vec_index, cand_vec, args.topk, args.timeout)

    report = build_report(queries, baseline_runs, candidate_runs)
    report["mode"] = "hybrid" if args.hybrid else "vector"
    report["baseline_name"] = args.baseline
    report["candidate_name"] = args.candidate

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"embedding_eval_{ts}.json"
    md_path = out_dir / f"embedding_eval_{ts}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
    md = render_markdown(report, args.baseline, args.candidate)
    md_path.write_text(md, encoding="utf-8")

    print(f"[OK] report -> {json_path}")
    print(f"[OK] report -> {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
