# B-0622 — Book Recommendation Tool Pipeline (Seed -> Candidates -> Explain)

## Priority
- P1

## Dependencies
- B-0620
- B-0621

## Goal
추천을 RAG 텍스트 생성이 아닌 카탈로그 기반 Tool 파이프라인으로 전환해 환각 추천을 차단한다.

## Why
- 추천은 문서 검색보다 catalog retrieval/유사도 계산이 핵심

## Scope
### 1) Pipeline stages
- seed 도서 식별
- candidate 생성(카테고리/유사도/재고/가격 제약)
- explanation 생성(LLM, 근거 제한)

### 2) Safety filters
- 존재하지 않는 도서/재고 없음/판매중지 제외
- confidence 낮은 seed는 disambiguation으로 전환

### 3) Contract
- 추천 결과에 `recommendation_reason`, `source_features`, `candidate_score` 포함

## DoD
- 존재하지 않는 도서 추천이 0건
- seed 식별 실패 시 안전한 되묻기 경로가 동작
- 추천 결과가 선택 UX와 연동된다.

## Interfaces
- recommendation tool endpoint
- chat orchestrator recommendation route

## Observability
- `chat_recommend_seed_resolve_total{result}`
- `chat_recommend_candidate_total{result}`

## Test / Validation
- hallucinated-book negative tests
- seed ambiguity tests
- recommendation contract tests

## Codex Prompt
Build a tool-first recommendation pipeline:
- Resolve seed book, generate catalog-backed candidates, and then explain.
- Filter unavailable/nonexistent books before response composition.
- Return structured recommendation reasons and scores.
