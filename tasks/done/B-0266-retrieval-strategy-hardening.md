# B-0266 — Search Service Retrieval Strategy (BM25 + Vector + Fusion/RRF) 플러그인화

## Goal
Search Service(SR)에 **Hybrid Search**를 운영형으로 넣는다.

- BM25(doc-level) + Vector(chunk-level) + Fusion(RRF) 기본 지원
- retrieval/fusion/rerank 단계를 **전략(Strategy) 플러그인**으로 분리
- 예산(budget) 기반(topN/topK/topR)으로 비용/지연을 통제
- 실패 시 degrade(bm25-only / fused-only) 가능

## Background
- SR은 오케스트레이터: QS 결과를 받아 후보를 뽑고 합치고(퓨전) 리랭킹 호출 후 응답 조립.
- Hybrid는 “품질”에 큰 영향을 주지만, 없으면 운영/비용/지연 통제가 안 된다.
- 점수 튜닝 지옥을 피하려면 초기 기본값은 **RRF**가 정답.

## Scope
### 1) 내부 파이프라인 구조(필수)
- `RetrievalStrategy`
  - BM25Retrieval (OpenSearch book_catalog)
  - VectorRetrieval (OpenSearch book_chunks + query embedding)
- `FusionStrategy`
  - RRFusion (default)
  - (optional) WeightedFusion (phase10/B-0303로 미룸)
- `RerankStrategy`
  - LTR-only / CrossEncoder / TwoStage(LTR→CE) (RS/MIS 연계)
- `PipelineOrchestrator`
  - budget/timeouts 적용
  - partial failure handling
  - debug/explain payload 준비(B-0268)

### 2) BM25(doc-level) Retrieval
- index: `books_doc_v*` (alias `books_doc_read`)
- query:
  - multi_match(title, author, series, aliases, keywords)
  - filters(kdc/year/lang/availability)
  - highlight/snippet(옵션)
- output:
  - `bm25_rank[doc_id] = rank`
  - store: title/author/summary for rerank inputs

### 3) Vector(chunk-level) Retrieval (hybrid일 때)
- index: `books_chunks_v*` (alias `books_chunks_read`)
- knn query:
  - embedding(query) → topK chunks
  - collapse by doc_id (chunk→doc 승격)
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
  - 한쪽만 존재해도 포함(“둘 중 하나라도 강하면 살리는” 성질)

### 5) Outputs (downstream)
- rerank candidates payload:
  - query_context + candidates(topR) with text fields + best_chunk snippet
- SR response assembly:
  - total/aggregation, items, pipeline info(retrieval mode, fusion, rerank)

## Non-goals
- embedding 모델 자체 구현(경로는 B-0266a로)
- degrade/서킷브레이커(=B-0267)
- debug/explain endpoint 상세(=B-0268)

## DoD
- SR 내부에 retrieval/fusion/rerank 전략 인터페이스가 분리되어 있음
- hybrid 모드에서 BM25+Vector+RRF가 동작
- budget(topN/topK/topR/topM) 파라미터가 강제됨
- vector 실패 시 bm25-only로 degrade 가능(연계: B-0267)
- 기본 기능 e2e: QS→SR(hybrid)→RS/MIS rerank→응답 OK

## Interfaces
- Input: BFF→SR `/internal/search` (query_context 포함)
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
