# B-0302 — Query Embedding 캐시/핫쿼리 벡터 캐시(비용 절감)

## Goal
Hybrid 검색에서 query embedding 생성이 병목/비용이 되지 않도록:
- **q_norm → embedding vector** 캐시를 도입하고
- 핫쿼리에 대해 p99를 안정화한다.

## Background
- Hybrid(BM25+Vector)에서 query embedding 생성은:
  - 외부 호출(LLM/모델) 또는 MIS CPU/GPU 리소스를 사용
  - 캐시 적중 시 품질 변화 없이 비용/지연을 크게 줄일 수 있음

## Scope
### 1) Cache key 설계
- key: `emb:q:{model_version}:{locale}:{hash(q_norm)}`
- value: float32 vector (compressed 가능)
- TTL:
  - 기본 1~7일(쿼리 분포에 따라)
- Invalidation:
  - model_version이 바뀌면 자연 분리

### 2) Cache storage
- v1: Redis(바이너리 blob)
- 옵션: local LRU(서비스 인스턴스 내) + Redis 2-tier

### 3) SR 연동
- SR이 hybrid 요청 시:
  1) 캐시 조회(hit) → vector retrieval 진행
  2) miss → embedding 생성(서비스 경로는 B-0266a 선택안과 일치) → 캐시 저장
- timeout budget:
  - embedding 단계에 별도 timeout + 실패 시 bm25-only degrade

### 4) Metrics/Observability
- cache_hit_rate, cache_latency, vector_stage_latency
- miss 시 embedding 생성 실패율
- hotkey topN(옵션)

## Non-goals
- doc embedding 캐시(청킹 인덱싱 단계가 별도)
- semantic rewrite/RAG 캐시(그건 QS B-0264)

## DoD
- embedding cache가 실제로 동작(hit/miss 로그/메트릭)
- hybrid 검색 p99가 개선됨(전/후 비교)
- model_version별로 캐시가 분리되어 안전하다
- embedding 실패 시 bm25-only degrade가 작동한다

## Codex Prompt
Add query embedding caching for hybrid search:
- Implement Redis-based cache keyed by model_version+locale+q_norm hash storing float vectors.
- Integrate into SR hybrid pipeline: cache hit -> vector retrieval; miss -> generate embedding -> store -> retrieve.
- Add metrics for hit rate and latency, and ensure degrade to bm25-only on embedding timeout/failure.
