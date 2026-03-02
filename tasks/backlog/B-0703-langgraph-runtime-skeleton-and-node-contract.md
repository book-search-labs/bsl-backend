# B-0703 — LangGraph Runtime Skeleton + Node Contract

## Priority
- P0

## Dependencies
- B-0702

## Goal
기존 챗 엔진 파이프라인을 LangGraph 노드로 재구성할 수 있는 런타임 뼈대를 구축한다.

## Scope
### 1) Graph skeleton
- 노드 구성: `load_state -> understand -> policy_decide -> execute -> compose -> verify -> persist`
- 조건부 edge: `ASK/OPTIONS/CONFIRM/EXECUTE/ANSWER/FALLBACK`
- 공통 에러 핸들링 노드(`error_handler`) 도입

### 2) Node contract
- 모든 노드는 `ChatGraphState -> ChatGraphState` 함수형 계약 유지
- 노드별 입력/출력 필드 최소셋 문서화
- 노드 실패 시 `reason_code`와 `stage` 강제 기록

### 3) Legacy adapter
- 기존 `run_chat` 경로에서 LangGraph 런타임 호출 가능하도록 adapter 추가
- 기존 응답 스키마 변환기(compat response mapper) 제공

### 4) Engine switch
- OpenFeature 전 단계로 env flag 기반 임시 스위치(`QS_CHAT_ENGINE_MODE`) 유지
- `legacy`, `shadow`, `canary`, `agent` 동작 호환

## Test / Validation
- graph node unit tests
- route branch integration tests
- legacy vs graph equivalence smoke tests (20+ 시나리오)

## DoD
- read-only 인텐트에서 graph 엔진이 안정적으로 동작한다.
- 기존 `/chat` 응답 계약이 유지된다.
- 노드별 실패 원인이 trace에서 식별 가능하다.

## Codex Prompt
Build LangGraph runtime skeleton for chat:
- Wire core nodes and route-based edges.
- Enforce node state contract and failure metadata.
- Add adapter so legacy API response shape remains unchanged.
