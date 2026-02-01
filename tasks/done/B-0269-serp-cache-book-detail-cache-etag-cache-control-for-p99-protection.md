# B-0269 — SR Cache Layer: SERP 캐시 + Book Detail 캐시(ETag/Cache-Control)로 p99 방어

## Goal
Search Service/Serving 구간에서 **p99 지연을 안정화**하기 위해 캐시 레이어를 도입한다.

- **SERP 캐시**: 동일한 `q_norm + filters + sort + page` 조합의 결과를 짧게 캐싱
- **Book detail 캐시**: `/books/:id` 응답에 **ETag/Cache-Control** 적용 + (옵션) 서버 캐시
- 캐시는 “정확도”보다 “운영”을 위해: TTL 짧게, invalidation 단순하게

## Background
- 검색은 tail latency가 사용자 UX에 치명적(p95/p99).
- Hybrid + rerank + MIS 호출이 붙으면 비용/지연이 튄다.
- 핫쿼리/핫도서는 캐시로 거의 해결된다.

## Scope
### 1) SERP 캐시(필수)
- 저장소: Redis(권장) 또는 in-memory Caffeine(단일 인스턴스일 때만)
- key:
  - `serp:{hash(q_norm + filters + sort + page + size + mode + exp_bucket + policy_version)}`
- value:
  - 결과 items(최대 size*N), total, agg 요약, pipeline 요약
- TTL:
  - 5~30초(기본 10초) — 트래픽/신선도에 따라 조절
- guard:
  - payload size 제한(예: 200KB)
  - cache stampede 방지(락/soft TTL 선택)

### 2) Book detail 캐시(ETag/Cache-Control) (필수)
- 응답 헤더:
  - `ETag`: stable hash(material_id + updated_at + schema_version)
  - `Cache-Control`: `public, max-age=60` (환경별)
- 요청 처리:
  - If-None-Match 일치 → 304 반환
- 옵션(서버 캐시):
  - Redis에 material_id → detail payload 캐시(짧게 1~5분)

### 3) Invalidation(단순화)
- SERP 캐시:
  - TTL 만료로 자연 소멸(기본)
  - (선택) reindex alias swap 시 prefix flush
- Detail 캐시:
  - `updated_at` 변경으로 ETag가 바뀌므로 자연 갱신
  - (선택) admin update 이벤트 수신 시 Redis key 삭제

### 4) Observability
- hit/miss/bytes/eviction 모니터링
- p99 개선 전/후 비교 가능

## Non-goals
- 정교한 캐시 일관성(강한 invalidation)
- CDN 도입(Phase 9/I-0313~)

## DoD
- SERP 캐시가 동작(hit/miss 로그/메트릭)
- book detail 응답에 ETag/Cache-Control 적용 + 304 처리
- payload size guard, stampede 최소 방어
- 캐시 도입 후 p95/p99 감소 확인(간단 벤치 포함)

## Interfaces
- SR 내부: cache middleware/adapter
- Redis(있으면): serp cache + detail cache

## Metrics/Logs
- `sr_serp_cache_hit_total`, `sr_serp_cache_miss_total`
- `sr_detail_304_total`
- `sr_cache_payload_bytes_hist`
- log: request_id, cache_key_hash, hit/miss, ttl

## Codex Prompt
Implement SR caching:
- Add Redis-backed SERP cache with short TTL and payload size guard.
- Add ETag + Cache-Control handling for book detail, return 304 on If-None-Match.
- Add metrics for cache hit/miss and 304 counts.
- Ensure cache keys include query, filters, sort, paging, mode, experiment/policy version.
