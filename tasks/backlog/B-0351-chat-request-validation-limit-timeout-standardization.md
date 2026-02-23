# B-0351 — `/chat` 요청 유효성/한도/타임아웃 표준화

## Priority
- P0 (Chat 안정화 선행)

## Dependencies
- B-0350 (장애 재현 키트)

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

## Non-goals
- 답변 품질 알고리즘 튜닝

## DoD
- invalid payload가 모두 400 + 표준 에러 포맷으로 반환
- timeout이 모호한 500이 아니라 `chat_timeout`으로 반환
- 프론트에 표시되는 오류가 한국어 가이드 메시지 포함
- Error code matrix가 `docs/API_SURFACE.md`와 일치

## Interfaces
- `POST /v1/chat`
- `contracts/chat-request.schema.json`
- `contracts/chat-response.schema.json`

## Observability
- `chat_validation_fail_total{reason}`
- `chat_timeout_total{stage}`
- `chat_error_total{code}`

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
