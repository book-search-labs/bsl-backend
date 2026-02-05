import argparse
import json
import math
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


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
                "fields": ["title_ko", "title_en", "authors.name_ko", "series_name", "publisher_name"],
            }
        },
    }
    data = post_json(f"{os_url.rstrip('/')}/{index}/_search", payload, timeout)
    return extract_doc_ids(data)


def rrf_scores(lex: List[str], vec: List[str], k: int) -> Dict[str, float]:
    scores: Dict[str, float] = defaultdict(float)
    for rank, doc_id in enumerate(lex, start=1):
        scores[doc_id] += 1.0 / (k + rank)
    for rank, doc_id in enumerate(vec, start=1):
        scores[doc_id] += 1.0 / (k + rank)
    return scores


def rrf_fuse(lex: List[str], vec: List[str], k: int) -> List[str]:
    scores = rrf_scores(lex, vec, k)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def fetch_sources(os_url: str, index: str, doc_ids: List[str], timeout: float) -> Dict[str, dict]:
    if not doc_ids:
        return {}
    payload = {"docs": [{"_index": index, "_id": doc_id} for doc_id in doc_ids]}
    data = post_json(f"{os_url.rstrip('/')}/_mget", payload, timeout)
    sources: Dict[str, dict] = {}
    for item in data.get("docs", []):
        doc_id = item.get("_id")
        source = item.get("_source") or {}
        if doc_id:
            sources[doc_id] = source
    return sources


def build_doc_text(doc_id: str, source: dict) -> str:
    if not source:
        return doc_id
    parts = []
    title_ko = source.get("title_ko")
    title_en = source.get("title_en")
    if title_ko:
        parts.append(str(title_ko))
    if title_en and title_en != title_ko:
        parts.append(str(title_en))

    authors = []
    for author in source.get("authors") or []:
        if isinstance(author, str):
            authors.append(author)
        elif isinstance(author, dict):
            name = author.get("name_ko") or author.get("name_en")
            if name:
                authors.append(name)
    if authors:
        parts.append(", ".join(authors))

    publisher = source.get("publisher_name")
    if publisher:
        parts.append(str(publisher))
    series = source.get("series_name")
    if series:
        parts.append(str(series))

    return " | ".join(parts) if parts else doc_id


def parse_json_options(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {}
    return json.loads(text)


def rerank_once(
    ranking_url: str,
    query: str,
    candidates: List[dict],
    timeout_seconds: float,
    base_options: dict,
    override_options: dict,
) -> tuple[List[str], float, bool]:
    options = dict(base_options)
    if override_options:
        options.update(override_options)
    payload = {
        "query": {"text": query},
        "candidates": candidates,
        "options": options,
    }
    started = time.time()
    response = post_json(f"{ranking_url.rstrip('/')}/rerank", payload, timeout_seconds)
    took_ms = response.get("took_ms")
    if took_ms is None:
        took_ms = int((time.time() - started) * 1000)
    doc_ids = [hit.get("doc_id") for hit in response.get("hits", []) if hit.get("doc_id")]
    debug = response.get("debug") or {}
    applied = debug.get("rerank_applied")
    return doc_ids, float(took_ms), bool(applied) if applied is not None else True


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


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = max(0, min(int(math.ceil((p / 100.0) * len(values))) - 1, len(values) - 1))
    return values[idx]


def evaluate_runs(
    queries: List[dict],
    runs: Dict[str, List[str]],
    rerank_applied: Dict[str, bool],
    rerank_latency: Dict[str, float],
) -> Tuple[dict, List[dict]]:
    ndcg_values = []
    mrr_values = []
    recall_values = []
    zero_results = 0
    cases = []

    applied_flags = []
    latency_values = []

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
        recall = recall_at_k(rels, total_rels, 100)
        ndcg_values.append(ndcg)
        mrr_values.append(mrr)
        recall_values.append(recall)
        cases.append({"qid": qid, "query": item.get("query"), "ndcg": ndcg, "mrr": mrr, "recall": recall})

        if qid in rerank_applied:
            applied_flags.append(1 if rerank_applied[qid] else 0)
        if qid in rerank_latency:
            latency_values.append(rerank_latency[qid])

    count = max(len(queries), 1)
    metrics = {
        "ndcg_10": sum(ndcg_values) / count,
        "mrr_10": sum(mrr_values) / count,
        "recall_100": sum(recall_values) / count,
        "zero_result_rate": zero_results / count,
        "query_count": len(queries),
    }
    if applied_flags:
        metrics["rerank_call_rate"] = sum(applied_flags) / len(applied_flags)
    if latency_values:
        metrics["rerank_latency_ms_avg"] = sum(latency_values) / len(latency_values)
        metrics["rerank_latency_ms_p50"] = percentile(latency_values, 50)
        metrics["rerank_latency_ms_p95"] = percentile(latency_values, 95)
    return metrics, cases


def build_report(
    queries: List[dict],
    baseline_runs: Dict[str, List[str]],
    candidate_runs: Dict[str, List[str]],
    candidate_applied: Dict[str, bool],
    candidate_latency: Dict[str, float],
) -> dict:
    baseline_metrics, baseline_cases = evaluate_runs(queries, baseline_runs, {}, {})
    candidate_metrics, candidate_cases = evaluate_runs(queries, candidate_runs, candidate_applied, candidate_latency)

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
    lines.append(f"# Rerank Eval Report ({baseline_name} -> {candidate_name})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Baseline | Candidate | Diff |")
    lines.append("| --- | --- | --- | --- |")
    for key in ["ndcg_10", "mrr_10", "recall_100", "zero_result_rate"]:
        base = report["baseline"].get(key, 0.0)
        cand = report["candidate"].get(key, 0.0)
        diff = report["diff"].get(key, 0.0)
        lines.append(f"| {key} | {base:.4f} | {cand:.4f} | {diff:+.4f} |")

    if "rerank_call_rate" in report["candidate"]:
        lines.append("")
        lines.append("## Rerank stats")
        call_rate = report["candidate"].get("rerank_call_rate", 0.0)
        lat_avg = report["candidate"].get("rerank_latency_ms_avg", 0.0)
        lat_p50 = report["candidate"].get("rerank_latency_ms_p50", 0.0)
        lat_p95 = report["candidate"].get("rerank_latency_ms_p95", 0.0)
        lines.append(f"- rerank_call_rate: {call_rate:.3f}")
        lines.append(f"- rerank_latency_ms_avg: {lat_avg:.1f}")
        lines.append(f"- rerank_latency_ms_p50: {lat_p50:.1f}")
        lines.append(f"- rerank_latency_ms_p95: {lat_p95:.1f}")

    lines.append("")
    lines.append("## Improved cases")
    for item in report.get("improved_cases", []):
        lines.append(f"- {item['qid']}: {item['query']} (\u0394NDCG={item['delta']:+.4f})")

    lines.append("")
    lines.append("## Regressed cases")
    for item in report.get("regressed_cases", []):
        lines.append(f"- {item['qid']}: {item['query']} (\u0394NDCG={item['delta']:+.4f})")

    return "\n".join(lines)


def compare_reports(baseline: dict, candidate: dict, max_drop: float, max_zero_increase: float) -> List[str]:
    errors = []
    for key in ["ndcg_10", "mrr_10", "recall_100"]:
        base = baseline.get(key)
        cand = candidate.get(key)
        if base is None or cand is None:
            continue
        if cand < base - max_drop:
            errors.append(f"{key} dropped {base:.4f} -> {cand:.4f}")
    base_zero = baseline.get("zero_result_rate")
    cand_zero = candidate.get("zero_result_rate")
    if base_zero is not None and cand_zero is not None:
        if cand_zero > base_zero + max_zero_increase:
            errors.append(f"zero_result_rate increased {base_zero:.4f} -> {cand_zero:.4f}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerank offline evaluation")
    parser.add_argument("--queries", default="data/eval/rerank_queries.jsonl")
    parser.add_argument("--os-url", default="http://localhost:9200")
    parser.add_argument("--doc-index", default="books_doc_read")
    parser.add_argument("--vec-index", default="books_vec_read")
    parser.add_argument("--mis-url", default="http://localhost:8005")
    parser.add_argument("--mis-model", default="embed_ko_v1")
    parser.add_argument("--ranking-url", default="http://localhost:8004")
    parser.add_argument("--lex-topk", type=int, default=200)
    parser.add_argument("--vec-topk", type=int, default=200)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--rerank-topk", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--baseline-mode", choices=["fused", "rerank"], default="fused")
    parser.add_argument("--candidate-mode", choices=["fused", "rerank"], default="rerank")
    parser.add_argument("--baseline-rerank-options", default="")
    parser.add_argument("--candidate-rerank-options", default="")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--max-drop", type=float, default=0.02)
    parser.add_argument("--max-zero-increase", type=float, default=0.02)
    args = parser.parse_args()

    queries = load_queries(Path(args.queries))
    if not queries:
        print("[FAIL] no queries found")
        return 1

    query_texts = [item.get("query") or "" for item in queries]
    query_vectors = embed_queries_mis(args.mis_url, args.mis_model, query_texts, args.batch_size, args.timeout)

    baseline_runs: Dict[str, List[str]] = {}
    candidate_runs: Dict[str, List[str]] = {}
    candidate_applied: Dict[str, bool] = {}
    candidate_latency: Dict[str, float] = {}

    base_options = {"size": args.rerank_topk, "debug": True, "timeout_ms": int(args.timeout * 1000)}
    baseline_override = parse_json_options(args.baseline_rerank_options)
    candidate_override = parse_json_options(args.candidate_rerank_options)

    for item, vector in zip(queries, query_vectors):
        qid = item.get("qid")
        if not qid:
            continue
        query = item.get("query") or ""
        lex_hits = search_lexical(args.os_url, args.doc_index, query, args.lex_topk, args.timeout)
        vec_hits = search_vector(args.os_url, args.vec_index, vector, args.vec_topk, args.timeout)
        fused = rrf_fuse(lex_hits, vec_hits, args.rrf_k)

        candidate_ids = fused[: args.rerank_topk]
        sources = fetch_sources(args.os_url, args.doc_index, candidate_ids, args.timeout)
        lex_rank = {doc_id: idx + 1 for idx, doc_id in enumerate(lex_hits)}
        vec_rank = {doc_id: idx + 1 for idx, doc_id in enumerate(vec_hits)}
        scores = rrf_scores(lex_hits, vec_hits, args.rrf_k)

        candidates = []
        for doc_id in candidate_ids:
            source = sources.get(doc_id, {})
            features = {
                "lex_rank": lex_rank.get(doc_id),
                "vec_rank": vec_rank.get(doc_id),
                "rrf_score": scores.get(doc_id),
                "issued_year": source.get("issued_year"),
                "volume": source.get("volume"),
                "edition_labels": source.get("edition_labels"),
            }
            candidates.append(
                {
                    "doc_id": doc_id,
                    "doc": build_doc_text(doc_id, source),
                    "features": features,
                }
            )

        if args.baseline_mode == "rerank":
            doc_ids, took_ms, applied = rerank_once(
                args.ranking_url,
                query,
                candidates,
                args.timeout,
                base_options,
                baseline_override,
            )
            baseline_runs[qid] = doc_ids
        else:
            baseline_runs[qid] = fused

        if args.candidate_mode == "rerank":
            doc_ids, took_ms, applied = rerank_once(
                args.ranking_url,
                query,
                candidates,
                args.timeout,
                base_options,
                candidate_override,
            )
            candidate_runs[qid] = doc_ids
            candidate_latency[qid] = took_ms
            candidate_applied[qid] = applied
        else:
            candidate_runs[qid] = fused

    report = build_report(queries, baseline_runs, candidate_runs, candidate_applied, candidate_latency)
    report["baseline_name"] = "fused_rrf" if args.baseline_mode == "fused" else "rerank_baseline"
    report["candidate_name"] = "rerank" if args.candidate_mode == "rerank" else "fused_rrf"
    report["baseline_mode"] = args.baseline_mode
    report["candidate_mode"] = args.candidate_mode
    report["baseline_rerank_options"] = baseline_override
    report["candidate_rerank_options"] = candidate_override

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rerank_eval_{ts}.json"
    md_path = out_dir / f"rerank_eval_{ts}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
    md = render_markdown(report, report["baseline_name"], report["candidate_name"])
    md_path.write_text(md, encoding="utf-8")

    print(f"[OK] report -> {json_path}")
    print(f"[OK] report -> {md_path}")

    if args.gate and args.baseline_report:
        with open(args.baseline_report, "r", encoding="utf-8") as handle:
            baseline_report = json.load(handle)
        errors = compare_reports(baseline_report.get("candidate", {}), report.get("candidate", {}), args.max_drop, args.max_zero_increase)
        if errors:
            print("[FAIL] rerank regression gate failed:")
            for error in errors:
                print(f"  - {error}")
            return 2
        print("[OK] rerank regression gate passed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
