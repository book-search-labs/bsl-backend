# B-0314 — Embedding Cache + 비용 절감 (ingest reuse + query embedding cache)

## Goal
real embedding 도입 후 비용/지연을 줄이기 위해:
- ingest 단계에서 동일 `vector_text_hash`는 embedding을 재사용
- online 검색에서 query embedding도 Redis 캐시로 재사용(옵션)

## Why
- NLK 데이터는 재실행/증분 시 동일 레코드가 반복될 수 있다.
- hot query는 반복되며 query embedding 캐시는 hybrid latency를 줄인다.

## Scope
1) ingest embedding reuse
- `vector_text_hash` 기준으로 embedding 재사용
- 구현 옵션:
  - Redis 캐시(옵션)
- 캐시 사이즈/TTL 정책 명시
- 캐시 hit/miss 로깅

2) query embedding cache(옵션, Search Service 연동)
- key: hash(q_norm + model_version)
- value: vector(float[])
- TTL: 5~30분(핫쿼리 중심)

## Non-goals
- 정교한 캐시 일관성(버전별 eviction)은 2차 고도화
- feature store와의 통합은 별도

## Interfaces / Contracts
- ingest cache store schema(선택):
  - `emb_cache(hash TEXT PRIMARY KEY, dim INT, vector BLOB, model TEXT, created_at)`
- redis key:
  - `emb:q:{model}:{sha256(q_norm)}`

## Design Notes
- model_version이 바뀌면 캐시 키에 model 포함하여 자동 무효화.
- 벡터는 float32로 직렬화(예: numpy.tobytes)하여 저장.

## DoD (Definition of Done)
- 동일 raw 파일을 2회 ingest 시 embed 호출 횟수/시간이 유의미하게 감소
- 캐시 hit/miss 메트릭/로그 노출
- 캐시가 꺼져도 정상 동작(기능 플래그)

## Files / Modules
- `scripts/ingest/ingest_opensearch.py` (cache 적용)
- (신규) `scripts/ingest/embedding_cache.py`
- (옵션) `search-service` query embedding cache 모듈

## Commands (examples)
```bash
# ingest with local embedding cache enabled
EMBED_PROVIDER=mis EMBED_CACHE=sqlite EMBED_CACHE_PATH=data/cache/emb.sqlite   python scripts/ingest/ingest_opensearch.py
```

## Codex Prompt (copy/paste)
```text
Implement B-0314:
- Add embedding reuse in ingestion keyed by vector_text_hash using a local sqlite cache (default) with optional Redis.
- Add flags: EMBED_CACHE=off|sqlite|redis, EMBED_CACHE_PATH, EMBED_CACHE_TTL_SEC.
- Record cache hit/miss metrics and ensure ingestion still works when cache is off.
- (Optional) add query embedding Redis cache in Search Service keyed by (model_version, q_norm hash).
```
