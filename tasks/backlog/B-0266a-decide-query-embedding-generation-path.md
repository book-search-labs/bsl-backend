# B-0266a — Query Embedding 생성 경로 확정 (OS 모델 vs Inference 경로)

## Goal
Hybrid 검색의 필수 요소인 **Query Embedding 생성 경로**를 확정/구현한다.

선택지:
1) OpenSearch 내 모델(플러그인/ML 기능 사용)
2) 별도 Inference 경로 (권장: MIS에 흡수 또는 별도 Embedding Service)

BSL 운영형 기준으로는 “서비스 통제/버전/관측/비용” 때문에 (2) 쪽이 유리.

## Background
- Vector retrieval은 query embedding이 없으면 불가능.
- embedding 경로가 흔들리면 SR의 지연/장애 모드가 불안정해진다.
- MIS로 통합하면 모델 배포/롤백/스케일/큐잉을 한 곳에서 처리 가능.

## Scope
### 1) Decision + ADR (필수)
- `ADR-00xx-embedding-path.md`
  - 선택한 옵션, 장단점, 운영 리스크, 롤백 플랜

### 2) API contract (option 2)
- MIS에 endpoint 추가:
  - POST `/v1/embeddings`
  - req: { request_id, text, model, options(max_len, normalize) }
  - res: { embedding: float[], dim, model_version, latency_ms }
- caching hint:
  - `embedding_cache_key` 반환(옵션)

### 3) SR integration
- SR이 vector retrieval 시:
  - cache hit → embedding 사용
  - cache miss → MIS 호출
- fallback:
  - embedding timeout/fail → vector retrieval skip → bm25-only

### 4) Cache (optional but recommended)
- Redis:
  - key: hash(q_norm + model_version)
  - TTL: 1h~24h (핫쿼리 위주)
- guard:
  - max size, eviction 정책

## Non-goals
- embedding model training
- vector index 설계(이미 별도 티켓/설계에 포함)

## DoD
- ADR로 embedding 경로 확정
- contract(OpenAPI/JSON schema) 추가
- SR에서 embedding 호출 및 timeout 시 degrade
- (옵션) Redis embedding cache 적용
- smoke test: q_norm → embedding → chunk knn → results

## Observability
- metrics:
  - embedding_requests_total
  - embedding_cache_hit_rate
  - embedding_latency_ms
  - embedding_degrade_total
- logs:
  - request_id, q_hash, model_version, cache_hit, timeout

## Codex Prompt
Finalize query embedding path:
- Write ADR deciding OS-native vs MIS embedding endpoint (prefer MIS).
- Add /v1/embeddings endpoint contract and implement in MIS (or stub).
- Integrate SR vector retrieval to call embeddings with caching and degrade on failure.
- Add metrics for cache hit and latency, and log request_id/model_version.
