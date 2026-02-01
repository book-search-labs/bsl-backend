# B-0318 — Search Service: Embedding HTTP hardening + cache + fallbacks

## Goal
Search Service가 `EMBEDDING_MODE=HTTP` 일 때 MIS `/v1/embed`를 호출한다.
이 경로를 운영 수준으로 강화한다:
- 시간예산(budget) 기반 timeout
- circuit breaker / bulkhead
- embedding cache(핫쿼리)
- 장애 시 vector retrieval degrade(bm25-only / lexical-only)

## Why
- vector retrieval의 p99가 전체 검색 p99를 망칠 수 있음.
- MIS 장애 시에도 검색은 “0건”이 아니라 “degraded 결과”라도 반환해야 함.
- 임베딩은 동일 쿼리 반복이 많아 캐시 효율이 큼.

## Scope
### In-scope
1) EmbeddingGateway hardening
- request timeout, retry(제한적), circuit breaker
- request_id/trace_id 전파

2) Query embedding cache
- key = hash(q_norm + model + normalize)
- short TTL(예: 5~60s) + size 제한
- 메모리 캐시(로컬)로 시작, 추후 Redis 확장 가능

3) degrade 정책
- embedding 실패 -> vector retrieval skip -> bm25-only
- vector 결과는 있지만 rerank 실패 -> fused 순서로 응답
- debug에 degrade reason codes 포함

4) Metrics 추가
- embed_call_latency, embed_fail_rate, cache_hit_rate
- degrade_rate (vector_disabled, embed_timeout, mis_down)

### Out-of-scope
- chunk index 품질 고도화(B-0304 범위)
- QS 2-pass 호출 전략(B-0262 범위)

## DoD
- MIS 다운/timeout 상황을 로컬에서 재현했을 때 검색이 정상 응답(lexical-only)으로 degrade 됨
- embed cache hit가 확인됨
- debug response에 reason code 포함
- unit/integration test 최소 1개 추가

## Files (expected)
- `services/search-service/src/main/java/com/bsl/search/embed/EmbeddingGateway.java`
- `services/search-service/src/main/java/com/bsl/search/embed/EmbeddingService.java`
- `services/search-service/src/main/java/com/bsl/search/service/HybridSearchService.java`
- `services/search-service/src/main/resources/application.yml`
- (테스트) `services/search-service/src/test/...`

## Commands
- run search-service with MIS URL
  - `EMBEDDING_MODE=HTTP EMBEDDING_BASE_URL=http://localhost:9000 ...`
- simulate MIS down and confirm degrade

## Codex Prompt
- Harden Search Service embedding HTTP path: timeouts, circuit breaker, cache, degrade policies.
- Add minimal tests and metrics; keep existing env variables compatible.
