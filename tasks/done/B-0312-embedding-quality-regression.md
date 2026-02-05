# B-0312 — Vector Index Mapping v2 (dim/metric/HNSW) + Alias Wiring

## Goal
real embedding 도입에 맞춰 OpenSearch vector index를 **v2**로 재정의한다.  
모델 dim/metric/HNSW 파라미터를 명시하고, 기존 운영 표준인 alias(read/write) 구조를 유지한다.

## Why
- toy(1024-d) → real(예: 768-d) 전환 시 기존 매핑으로는 저장/검색이 불가능하거나 품질이 깨진다.
- index v2로 분리하면 blue/green 방식으로 안전하게 전환할 수 있다.

## Scope
1) `books_vec_v2` 인덱스 템플릿/매핑 추가
- embedding field: knn_vector (dim = EMBED_DIM, metric = cosine 등)
- metadata: doc_id, vector_text_hash, updated_at 등
- HNSW: m, ef_construction, ef_search (기본값 + env override)

2) alias
- `books_vec_write` → v2 write
- `books_vec_read` → v2 read
- 전환은 alias swap으로 수행

3) bootstrap 스크립트 업데이트
- scripts/os_bootstrap_indices_v1_1.sh (또는 v1_2)에서 vec v2 생성/alias wiring 지원

## Non-goals
- reindex job orchestration(B-0223) 자체 구현은 별도
- chunk 인덱스는 B-0313(옵션)

## Interfaces / Contracts
OpenSearch index/alias:
- Index: `books_vec_v2`
- Alias: `books_vec_write`, `books_vec_read`

## Design Notes
- dim/metric은 모델과 반드시 일치해야 한다.
- 운영 튜닝은 기본값으로 시작하고, 부하테스트(I-0309) 결과로 파라미터 조정한다.

## DoD (Definition of Done)
- bootstrap 실행으로 `books_vec_v2` 생성 + alias wiring 완료
- ingest(B-0311)로 v2에 벡터 적재 성공
- Search Service가 `books_vec_read` alias로 knn query 수행 가능(테스트 쿼리 1개 포함)

## Files / Modules
- (신규) `opensearch/templates/books_vec_v2.json`
- `scripts/os_bootstrap_indices_v1_1.sh` (또는 버전업 스크립트)
- (선택) `docs/opensearch/vec_v2.md` (파라미터 문서)

## Commands (examples)
```bash
# create vec v2 and wire aliases
bash scripts/os_bootstrap_indices_v1_1.sh

# verify
curl -s $OS_URL/_alias/books_vec_read | jq .
```

## Codex Prompt (copy/paste)
```text
Implement B-0312:
- Add OpenSearch vector index mapping/template for books_vec_v2 using real embedding dim/metric (cosine by default).
- Keep read/write aliases: books_vec_write and books_vec_read.
- Update bootstrap script to create the index if missing and wire aliases.
- Include a small verification snippet (curl) and a sample kNN query in docs or tests.
```
