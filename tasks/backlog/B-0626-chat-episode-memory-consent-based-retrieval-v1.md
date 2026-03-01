# B-0626 — Chat Episode Memory (Consent-based Retrieval) v1

## Priority
- P2

## Dependencies
- B-0601
- B-0612

## Goal
사용자 동의 기반 에피소드 메모리를 도입해 장기 대화 맥락 품질을 높이되 개인정보 보호를 보장한다.

## Why
- 장기 맥락은 유용하지만 무분별 저장은 프라이버시/규제 리스크를 높임

## Scope
### 1) Consent gate
- memory opt-in/opt-out 상태 관리
- 동의 없으면 장기 메모리 저장/검색 금지

### 2) Memory retrieval
- `summary_short` 중심 fact retrieval
- 민감 정보 필터링 후 retrieval

### 3) User control
- 메모리 조회/삭제 endpoint
- 메모리 사용 이유(explainability) 노출

## DoD
- opt-out 사용자는 장기 메모리가 저장되지 않는다.
- 메모리 조회/삭제가 사용자 단위로 동작한다.
- 개인정보 필터를 통과한 정보만 메모리로 사용된다.

## Interfaces
- memory store API
- privacy consent profile

## Observability
- `chat_memory_opt_in_total`
- `chat_memory_retrieval_total{result}`
- `chat_memory_delete_total`

## Test / Validation
- consent boundary tests
- memory delete e2e tests
- pii leakage regression tests

## Codex Prompt
Introduce consent-based episode memory:
- Store/retrieve long-term chat facts only for opted-in users.
- Filter sensitive data before memory persistence.
- Provide user-level memory inspection/deletion controls.
