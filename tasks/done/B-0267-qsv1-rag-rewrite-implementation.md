# File: tasks/backlog/B-0267-qsv1-rag-rewrite-implementation.md

# B-0267 — QS: Implement RAG_REWRITE strategy (candidate retrieval + rewrite)

## Goal
USER_EXPLICIT 또는 지정 조건에서 RAG 기반 query rewrite가 실제로 동작하도록 한다.
(후보 검색 → 컨텍스트 → rewrite 생성, citations는 RAG 챗 단계에서)

## Scope
- Candidate retrieval:
  - OpenSearch에서 title/author/series 후보 TopK 조회(간단 BM25)
  - 또는 alias dictionary/feature store
- LLM rewrite:
  - 후보들을 컨텍스트로 넣어 “검색용 짧은 질의”를 생성
  - JSON schema 강제(최소 `{ q_rewrite, confidence }`)
- fallback:
  - 후보 없음/지연 초과 시 REWRITE_ONLY 또는 SKIP로 degrade

## Non-goals
- RAG 챗(Answer generate, citations 강제)은 Phase 7(B-0282~)에서 다룸
- 복잡한 chunk 기반 retrieval은 범위 아님(초기 후보 기반 rewrite만)

## Interfaces
- `/query/enhance`:
  - strategy=RAG_REWRITE일 때 rewrite 결과가 바뀔 수 있음
  - response에 `rag: { candidate_count, source }` (optional debug)

## DoD
- RAG_REWRITE가 실제로 후보를 활용해 rewrite 가능
- metrics: rag_rewrite_attempt/hit/miss/degrade
- tests: candidate retrieval mock + LLM mock

## Files to Change
- `services/query-service/app/core/enhance.py`
- `services/query-service/app/core/rag_candidates.py` (new)
- tests
- contracts/examples (필요시)

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Implement RAG_REWRITE in QS enhance by retrieving candidates from OpenSearch (mock in tests) and calling LLM rewrite with schema validation.
Add metrics, degrade behavior, and tests.
