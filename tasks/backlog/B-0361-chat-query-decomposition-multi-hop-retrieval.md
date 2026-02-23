# B-0361 — Chat Query Decomposition + Multi-hop Retrieval

## Priority
- P2

## Dependencies
- B-0354

## Goal
복합 질문을 하위 질의로 분해해 검색 누락을 줄이고, 단계적 근거 결합 품질을 높인다.

## Why
- 긴 질문/복합 의도에서 단일 retrieval만으로는 근거 recall이 부족

## Scope
### 1) Query decomposition
- 복합 질문을 2~4개 하위 질의로 분해
- 질의별 retrieval 후 병합

### 2) Multi-hop evidence merge
- 질의별 근거 중복 제거
- 충돌 근거 처리 우선순위 규칙

### 3) Budget control
- 분해 질의 수 상한
- 단계별 latency budget

## DoD
- 복합 질문 평가셋에서 recall/groundedness 개선
- latency budget 내 동작

## Codex Prompt
Implement query decomposition for complex chat queries:
- Split multi-intent questions into sub-queries.
- Perform retrieval per sub-query and merge evidence with dedup.
- Respect latency and token budgets.
