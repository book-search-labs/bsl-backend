# B-0311 — Real Embedding via MIS `/v1/embed` (Ingest → MIS batch 호출)

## Goal
현재 `books_vec_write`의 벡터가 toy embedding이므로, ingest가 **실제 embedding**을 생성하도록 전환한다.  
Ingest는 `EMBED_PROVIDER=mis`일 때 **MIS `/v1/embed`** 를 배치로 호출해 벡터를 받아 저장한다.

## Why
- 의미 기반 검색 품질을 올리려면 real embedding이 필요하다.
- 모델 추론을 ingest 프로세스에 직접 넣으면 장애/성능/배포가 복잡해지므로 **MIS로 격리**한다.

## Scope
1) MIS에 `/v1/embed` 엔드포인트 추가
- Request: `{ model, texts[], normalize }`
- Response: `{ dim, vectors[][] }`
- 동시성 제한/타임아웃/워밍업 기본 탑재
- 배치 처리(가능하면 dynamic batching)

2) ingest_opensearch.py에 embedding provider 경로 추가
- 환경 변수:
  - `EMBED_PROVIDER=toy|mis|os` (default: mis)
  - `MIS_URL`, `EMBED_MODEL`, `EMBED_BATCH_SIZE`, `EMBED_TIMEOUT_SEC`, `EMBED_MAX_RETRY`
  - `EMBED_FALLBACK_TO_TOY=0/1`
- 실패 시 deadletter 기록, 체크포인트 유지

3) 일관성
- Search Service ToyEmbedder와의 '일치' 요구는 제거(이제 real embedding이 source of truth)
- Search Service의 query embedding도 동일 모델을 사용하도록 이후 티켓(B-0266a/B-0314)에서 맞춘다.

## Non-goals
- OpenSearch vector index mapping(v2)은 B-0312에서 처리
- query embedding cache 및 비용 절감은 B-0314에서 처리

## Interfaces / Contracts
### MIS `/v1/embed` (proposed)
Request:
```json
{ "model":"embed_ko_v1", "texts":["...","..."], "normalize":true }
```
Response:
```json
{ "dim":768, "vectors":[[0.1,-0.2,...], [...]] }
```

## Design Notes
- ingest는 batch 단위로 MIS 호출(예: 32~128)하여 throughput을 확보한다.
- retry는 idempotent하며, 실패 레코드는 deadletter로 남긴다.
- `vector_text_hash`를 함께 보내서(옵션) 서버 캐시가 가능하도록 확장 여지를 남긴다(현재는 클라 캐시 B-0314).

## DoD (Definition of Done)
- `EMBED_PROVIDER=mis`로 ingest 실행 시 `books_vec_write`에 real vectors가 저장됨
- MIS 장애/타임아웃 시:
  - `EMBED_FALLBACK_TO_TOY=0`: 해당 문서는 deadletter로 기록되고 ingest는 계속 진행
  - `EMBED_FALLBACK_TO_TOY=1`: toy로 대체(옵션)
- 로그/메트릭(최소):
  - embed_latency_ms, embed_fail_total, embed_batch_size

## Files / Modules
- MIS 서비스 코드 (예: `services/mis/` 또는 `mis/`)
- `contracts/mis/openapi.yaml` (추가/갱신)
- `scripts/ingest/ingest_opensearch.py` (provider 경로)

## Commands (examples)
```bash
# MIS 실행(예)
docker compose up -d mis

# ingest with real embeddings
ENABLE_VECTOR_INDEX=1 EMBED_PROVIDER=mis MIS_URL=http://localhost:9000 EMBED_MODEL=embed_ko_v1   EMBED_BATCH_SIZE=32 EMBED_TIMEOUT_SEC=5 EMBED_MAX_RETRY=3   python scripts/ingest/ingest_opensearch.py
```

## Codex Prompt (copy/paste)
```text
Implement B-0311:
- Add MIS endpoint POST /v1/embed that accepts {model, texts[], normalize} and returns {dim, vectors[][]}.
- Add batching and basic concurrency limits/timeouts in MIS.
- Update scripts/ingest/ingest_opensearch.py to support EMBED_PROVIDER=mis and call MIS in batches with retries/timeouts.
- Keep checkpoint/resume and deadletter behavior intact.
- Add env flags: MIS_URL, EMBED_MODEL, EMBED_BATCH_SIZE, EMBED_TIMEOUT_SEC, EMBED_MAX_RETRY, EMBED_FALLBACK_TO_TOY.
- Emit basic logs/metrics for embed latency, failures, batch sizes.
```
