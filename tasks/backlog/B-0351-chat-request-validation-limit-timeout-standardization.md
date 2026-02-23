# B-0351 — `/chat` 요청 유효성/한도/타임아웃 표준화 (개정 v2)

## Priority
- P0 (Chat 안정화 선행)

## Dependencies
- B-0350 (장애 재현 키트)
- B-0391 (실서비스 출시 게이트)

## Goal
챗 API 요청 계약을 엄격히 검증하고, 초과/오류 상황을 일관된 응답으로 반환한다.

## Why
- 현재 프론트에서 `http_error`처럼 모호한 오류가 노출될 수 있음
- 입력 검증/제한/타임아웃 표준화가 사용자 체감 안정성의 핵심

## Scope
### 1) Request validation
- 필수 필드 검증: `q`, `session_id`, `options`
- 길이/크기 상한: query length, history size, `top_k`, `max_tokens`
- 허용 enum 검증: retrieval mode, language, response mode

### 2) Timeout/budget 표준
- stage timeout: rewrite/retrieve/rerank/generate
- global timeout과 stage timeout 분리
- timeout 초과 시 즉시 중단 + 표준 에러 반환

### 3) Error envelope 통일
- 모든 오류 응답에 `error.code`, `error.message`, `trace_id`, `request_id` 강제
- 사용자 노출 메시지(한국어)와 운영 코드 분리

### 4) Error code matrix (신규)
- `chat_bad_request` (400)
- `chat_payload_too_large` (413)
- `chat_rate_limited` (429)
- `chat_timeout` (504)
- `chat_dependency_error` (502)
- `chat_internal_error` (500)

### 5) 계약 검증 자동화
- contracts 예시 추가/보강
- invalid/oversize/timeout 케이스 테스트 추가

### 6) Client recovery contract (신규)
- 에러 응답에 `reason_code`, `recoverable`, `retry_after_ms`, `next_action` 필드 표준화
- 프론트가 사용자에게 즉시 안내 가능한 복구 동작(`재시도`, `입력수정`, `상담전환`)을 machine-readable로 제공
- 미정의 에러는 `chat_internal_error`로 fail-closed 매핑

## Non-goals
- 답변 품질 알고리즘 튜닝

## DoD
- invalid payload가 모두 400 + 표준 에러 포맷으로 반환
- timeout이 모호한 500이 아니라 `chat_timeout`으로 반환
- 프론트에 표시되는 오류가 한국어 가이드 메시지 포함
- Error code matrix가 `docs/API_SURFACE.md`와 일치
- `recoverable/next_action`이 위젯 복구 UX(U-0151/U-0153)와 연동됨

## Interfaces
- `POST /v1/chat`
- `contracts/chat-request.schema.json`
- `contracts/chat-response.schema.json`

## Observability
- `chat_validation_fail_total{reason}`
- `chat_timeout_total{stage}`
- `chat_error_total{code}`
- `chat_error_recovery_hint_total{next_action}`

## Test Matrix
- 필수 필드 누락
- history 과다
- 토큰 상한 초과
- stage timeout (rewrite/retrieve/generate)
- dependency 5xx/429 전파

## Codex Prompt
Harden chat request validation and timeout policy:
- Add strict request validators and payload limits.
- Standardize timeout handling and error envelope with fixed error codes.
- Add contract examples and tests for invalid/oversize/timeout paths.

## Implementation Update (2026-02-23, Bundle 3)
- [x] chat runtime validation 추가
  - `message.content` 길이 제한 (`QS_CHAT_MAX_MESSAGE_CHARS`)
  - `history` 턴 수 제한 (`QS_CHAT_MAX_HISTORY_TURNS`)
  - 전체 payload 문자 수 제한 (`QS_CHAT_MAX_TOTAL_CHARS`)
  - `session_id` 패턴/길이 검증 (`QS_CHAT_SESSION_ID_PATTERN`, `QS_CHAT_SESSION_ID_MAX_LEN`)
  - `top_k` 상한 검증 (`QS_CHAT_MAX_TOP_K`)
- [x] 제한 위반 시 recovery contract 기반 fallback 반환
  - reason_code: `CHAT_BAD_REQUEST`, `CHAT_INVALID_SESSION_ID`, `CHAT_MESSAGE_TOO_LONG`, `CHAT_HISTORY_TOO_LONG`, `CHAT_PAYLOAD_TOO_LARGE`, `CHAT_TOP_K_TOO_LARGE`
- [x] observability 보강
  - `chat_validation_fail_total{reason}` 메트릭 추가
- [x] 테스트 보강
  - `run_chat`/`run_chat_stream` 제한 위반 케이스 추가
  - `/chat` invalid JSON 요청 400 에러 포맷 테스트 추가
