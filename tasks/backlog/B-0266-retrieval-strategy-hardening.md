# B-0266 — Search Service Retrieval Strategy (BM25 + Vector + Fusion/RRF) Plugin

## Goal
In Search Service (SR), you can use the "Hybrid Search**".

- BM25(doc-level) + Vector(chunk-level) + Fusion(RRF)
- retrieval/fusion/rerank step **Strategy plugin**
- Control cost/continuous with budget (budget)-based (topN/topK/topR)
- degrade(bm25-only/fused-only) is possible when failed

## Background
- SR is an aqueous generator: QS resulting in a number of candidates and consolidated (pure) re-langing calls after a response assembly.
- Hybrid has a large impact on “quality”, but there is no operation/cost/release control.
- In order to avoid the score tuning hell, the initial default is **RRF**.

## Scope
### 1) Internal pipeline structure (required)
- `RetrievalStrategy`
  - BM25Retrieval (OpenSearch book_catalog)
  - VectorRetrieval (OpenSearch book_chunks + query embedding)
- `FusionStrategy`
  - RRFusion (default)
  - (optional) WeightedFusion (single room with phase10/B-0303)
- `RerankStrategy`
  - LTR -only / CrossEncoder / TwoStage(LTR→CE) (RS/MIS Link)
- `PipelineOrchestrator`
  - budget/timeouts coverage
  - partial failure handling
  - debug/explain payload preparation(B-0268)

### 2) BM25(doc-level) Retrieval
- index: `books_doc_v*` (alias `books_doc_read`)
- query:
  - multi_match(title, author, series, aliases, keywords)
  - filters(kdc/year/lang/availability)
  - highlight/snippet(optional)
- output:
  - `bm25_rank[doc_id] = rank`
  - store: title/author/summary for rerank inputs

### Vector (chunk-level) Retrieval (hybrid)
- index: `books_chunks_v*` (alias `books_chunks_read`)
- knn query:
  - embedding(query) → topK chunks
  - doc id
- output:
  - `vec_rank[doc_id] = rank`
  - `best_chunk[doc_id] = {chunk_id, snippet, score}`

### 4) Fusion (RRF default)
- input ranks:
  - bm25_rank, vec_rank
- output:
  - fused list of doc_ids (topM)
- params:
  - `rrf_k` (e.g., 60)
  - `topM_docs` (e.g., 200~300)
- rule:
  - Includes only one side (the “Saving” property if one of them is strong)

### 5) Outputs (downstream)
- rerank candidates payload:
  - query_context + candidates(topR) with text fields + best_chunk snippet
- SR response assembly:
  - total/aggregation, items, pipeline info(retrieval mode, fusion, rerank)

## Non-goals
- embedding model itself implementation (with B-0266a)
- degrade / Circuit Breaker(=B-0267)
- debug/explain endpoint details(=B-0268)

## DoD
- The retrieval/fusion/rerank strategy interface inside SR is separated
- BM25+Vector+RRF in hybrid mode
- (topN/topK/topR/topM)
- bm25-only
- Basic Function e2e: QS→SR(hybrid)→RS/MIS rerank→Request OK

## Interfaces
- Input: BFF→SR   TBD   (including query context)
- Downstream:
  - OpenSearch book_catalog, book_chunks
  - (optional) Embedding inference (B-0266a)
  - RS/MIS rerank

## Observability
- metrics:
  - sr_retrieval_latency_ms{type=bm25|vector}
  - sr_fusion_latency_ms{type=rrf}
  - sr_candidates_count{stage=bm25|vector|fused|rerank}
  - sr_vector_degrade_total
- logs:
  - request_id, mode, topN/topK/topR, degrade_reason

## Codex Prompt
Implement SR retrieval strategy plugin system:
- Add BM25 doc-level retrieval against books_doc_read.
- Add optional vector chunk-level retrieval against books_chunks_read and collapse to doc.
- Implement RRF fusion with configurable rrf_k and topM.
- Enforce budgets and prepare candidate payload for rerank.
- Add metrics/logs for stage latency and candidate counts.
