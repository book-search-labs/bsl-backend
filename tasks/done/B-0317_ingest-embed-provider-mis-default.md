# B-0317 — Ingest: use MIS /v1/embed as default embedding provider (with cache + fallback)

## Goal
`scripts/ingest/ingest_opensearch.py`에서 벡터 생성이 여전히 toy 중심/혼재되어 있다.
Ingest가 **기본 provider를 MIS(/v1/embed)** 로 사용하도록 정리하고,
대량 ingest에서 비용/지연을 제어하기 위한 캐시/재시도/실패 처리까지 운영 수준으로 맞춘다.

## Why
- ingest가 만드는 벡터 품질이 vector index 전체 품질을 결정한다.
- MIS를 SSOT(추론 단일 진입점)로 두면 모델 교체/버전관리/관측이 쉬워진다.
- 대량 ingest에서 같은 텍스트 반복 임베딩이 많아 캐시 효율이 크다.

## Scope
### In-scope
1) provider 기본값 변경
- `EMBED_PROVIDER=mis` 기본
- `MIS_URL` 필수(없으면 명확히 에러)
- `EMBED_FALLBACK_TO_TOY=1` 옵션 유지(단, 기본은 0 권장)

2) batching/retry/timeout 안정화
- `EMBED_BATCH_SIZE`, `EMBED_TIMEOUT_SEC`, `EMBED_MAX_RETRY`
- partial 실패 시 deadletter 기록 + 다음 배치 진행

3) embedding cache를 ingest path에 “필수 옵션”으로 정리
- sqlite/redis/off 옵션
- hit/miss 통계 로그

4) vector_text 규칙과 해시 기반 캐시 키 고정
- key = `vector_text_hash + model + normalize`
- 벡터 float32 직렬화/역직렬화 안정화

### Out-of-scope
- canonical ETL 자체 개선(B-0222 범위)
- OpenSearch alias switch 자동화(B-0223 범위)

## Interfaces
- MIS `/v1/embed` 호출 표준화
- ingest env 문서 업데이트

## Observability
- ingest 로그에 embedding 관련 카운터 출력
  - embed_calls, embed_failed_batches, cache_hit, cache_miss
- deadletter 포맷 표준
  - file: `data/nlk/deadletter/embed_fail_*.ndjson`

## DoD
- ENABLE_VECTOR_INDEX=1 ingest에서 **항상 MIS embed**를 사용(설정으로 toy fallback 가능)
- 대량 ingest 중 embed 장애 시에도 전체 ingest가 “중단”이 아니라 “부분 실패 기록 + 진행” 가능
- cache hit/miss가 명확히 출력되고 동작 확인
- README/문서 업데이트

## Files (expected)
- `scripts/ingest/ingest_opensearch.py`
- `scripts/ingest/embedding_cache.py`
- `scripts/ingest/vector_text.py` (hash 사용/연동)
- `docs/ingest/opensearch.md` (또는 유사 문서)

## Commands
- local ingest (예시)
  - `EMBED_PROVIDER=mis MIS_URL=http://localhost:9000 ENABLE_VECTOR_INDEX=1 EMBED_CACHE=sqlite python scripts/ingest/ingest_opensearch.py`
- verify vectors exist
  - `curl $OS_URL/books_vec_read/_search?q=doc_id:...`

## Codex Prompt
- Make MIS /v1/embed the default embedding provider for ingestion.
- Ensure batching/retry/timeout/deadletter are robust.
- Ensure embedding cache keying uses vector_text_hash + model + normalize.
- Update docs and keep flags backward compatible.
