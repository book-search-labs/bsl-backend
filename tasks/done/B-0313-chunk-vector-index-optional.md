# B-0313 — Chunk 기반 Vector Index (옵션): chunk kNN → doc 승격 → RRF fusion

## Goal
doc-level vector만으로는 세부 내용(요약/설명/목차)이 반영되지 않아 semantic recall이 제한될 수 있다.  
옵션으로 chunk 기반 인덱스를 도입해 **chunk kNN** 결과를 doc로 승격하고, BM25와 **RRF fusion**으로 합치는 하이브리드 파이프라인을 지원한다.

## Why
- 도서 검색은 제목이 짧거나 모호한 경우가 많아, 설명/소개/목차 등 chunk가 도움이 된다.
- RAG 챗봇(Phase 7)과 인프라를 공유할 수 있다.

## Scope
1) `book_chunks_v1` 인덱스(또는 books_chunks_v1) 정의
- chunk_id, doc_id, section, text, embedding, offsets(선택), metadata

2) chunk 생성(초기)
- 책 소개/요약/키워드가 있으면 섹션 단위로 chunk 생성
- 없으면 title+author+publisher 기반 pseudo-chunk만이라도 생성(최소)

3) 검색 파이프라인(SR 연동)
- chunk kNN topK → doc_id별 best chunk score로 승격
- BM25 docs와 RRF fusion

## Non-goals
- 고급 chunking(섹션 파서/PDF)은 RAG Phase에서 확대
- 완전한 RAG citations UI는 Phase 7 범위

## Interfaces / Contracts
- OpenSearch index: `book_chunks_v1`
- SR 내부 fusion 인터페이스는 B-0266/0266a와 정합성 유지

## Design Notes
- chunk → doc 승격 시 다양성/중복 제거(같은 doc_id 여러 chunk 중 best만)
- chunk text는 embedding 입력에 heading_path 같은 라벨을 섞으면 품질이 좋아짐

## DoD (Definition of Done)
- 최소 1만 chunk 샘플로 인덱싱 성공
- chunk kNN 쿼리로 유사 질의에서 doc recall이 개선되는 케이스 5개 문서화

## Files / Modules
- `opensearch/templates/book_chunks_v1.json` (신규)
- `scripts/ingest/ingest_opensearch.py` (chunk 생성/적재 옵션)
- `search-service` (fusion 경로 연결: B-0266/0266a)

## Commands (examples)
```bash
# optional: enable chunk indexing
ENABLE_CHUNK_INDEX=1 python scripts/ingest/ingest_opensearch.py

# test knn on chunks
curl -s $OS_URL/book_chunks_v1/_search -H 'Content-Type: application/json' -d @scripts/os_queries/knn_chunk.json
```

## Codex Prompt (copy/paste)
```text
Implement optional B-0313:
- Define a chunk vector index (book_chunks_v1) and add an ingestion path that produces simple chunks (even pseudo-chunks).
- Add kNN query example and a doc-upgrade step (doc_id aggregation).
- Keep it feature-flagged so it doesn't affect current pipelines by default.
```
