# B-0350 — Chat 장애 재현 키트 (failure taxonomy + replay seed + deterministic harness)

## Goal
챗봇 장애를 "가끔 재현됨" 상태에서 벗어나, 요청 단위로 재현 가능한 체계를 만든다.

## Why
- 현재 "정상 동작하지 않음" 이슈의 원인 범주가 넓고 재현이 어려움
- 재현 가능성이 확보되어야 고도화 작업(품질/성능/안전)이 효과적으로 진행됨

## Scope
### 1) Failure taxonomy 표준화
- chat 실패 유형 코드 정의: timeout, retrieval_empty, citation_missing, llm_error, policy_block, parsing_error 등
- 서비스(QS/BFF/web-user) 공통 reason_code 매핑

### 2) Replay payload 저장/조회
- request_id, trace_id, 주요 입력, 게이트 결정값, retrieval 후보, 최종 에러코드 저장
- 운영자가 특정 실패 건을 재실행할 수 있는 replay endpoint 또는 script 제공

### 3) Deterministic harness
- 외부 의존(LLM/MIS/OS) stub 모드 지원
- 동일 입력에서 동일 결과가 나오도록 seed/temperature 제어

### 4) 관측성
- 실패 건에 replay_id 발급
- 로그/메트릭에서 replay_id로 교차 추적

## Non-goals
- 모델 품질 개선 자체(별도 티켓)

## DoD
- 운영 로그에서 실패 1건을 선택해 1회 내 재현 가능
- 실패 유형이 taxonomy 코드로 일관되게 분류됨
- 재현 결과와 원본 실패의 차이를 리포트로 확인 가능

## Interfaces
- `POST /internal/chat/replay`
- `GET /internal/chat/failures/{request_id}`

## Files (예시)
- `services/query-service/app/api/routes.py`
- `services/query-service/app/service/chat_orchestrator.py`
- `services/bff-service/src/main/java/com/bsl/bff/api/ChatController.java`
- `docs/RUNBOOK.md`

## Codex Prompt
Implement chat failure reproducibility kit:
- Add failure taxonomy codes and propagate them across QS/BFF responses.
- Persist replay payloads keyed by request_id/trace_id.
- Provide deterministic replay path with seeded/stubbed dependencies.
