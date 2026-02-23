# B-0359 — Chat Tool Calling v2 (주문/배송/환불 인텐트 연동 고도화)

## Priority
- P1

## Dependencies
- B-0351, B-0352, B-0354
- B-0364 (Tool schema registry, 선행 권장)

## Goal
챗봇이 주문/배송/환불 질의에서 추측 답변을 금지하고, 백엔드 실데이터 조회 결과만 기반으로 한국어 안내를 제공한다.

## Non-goals
- 신규 결제/환불 비즈니스 규칙 자체를 설계하지 않는다.
- 기존 Commerce API의 도메인 모델을 대규모 리팩터링하지 않는다.
- 관리자 전용 기능을 일반 사용자 챗 인터페이스에 노출하지 않는다.

## Scope
### 1) Intent routing + confidence gate
- 주문조회/배송조회/환불가능여부/환불진행상태/결제오류 인텐트 분류기 정의
- high-confidence 인텐트는 `tool_required=true`로 강제
- low-confidence 인텐트는 추가 질문(주문번호/기간/결제수단) 후 재분류

### 2) Tool contract and safe execution
- 모든 tool에 input/output JSON Schema 강제
- reason_code/error_code를 표준화해 BFF `error envelope`와 매핑
- tool 응답이 schema 불일치면 사용자 노출 없이 안전 fallback

### 3) AuthN/AuthZ and privacy
- `x-user-id`, `trace_id`, `request_id` 없으면 실행 금지
- 본인 소유 주문만 조회 허용, 타인 주문번호는 차단
- 민감 필드(전화번호/주소/결제수단 세부)는 마스킹 후 응답

### 4) Reliability and fallback
- tool timeout/retry/backoff 클래스 정의(lookup/read/policy별)
- 부분 실패 시 정책 안내 + 재시도 제안 + 고객센터 전환 경로
- 읽기 요청 idempotency 보장 및 duplicate call 억제

### 5) Response synthesis (Korean deterministic template)
- 동일 reason_code에서 동일 문장 구조를 생성하는 템플릿 구성
- 상태/날짜/금액/수수료는 tool 값만 주입
- 인용(citation)은 tool name + endpoint + timestamp를 포함

## Interfaces
- `POST /v1/chat`
- `GET /api/v1/orders/{orderId}`
- `GET /api/v1/shipments/by-order/{orderId}`
- `GET /api/v1/refunds/by-order/{orderId}`
- `POST /api/v1/refunds/quote` (optional)

## Data / Schema
- `chat_tool_call_audit` (new): request_id, user_id, intent, tool_name, status, error_code, latency_ms
- `chat_tool_policy` (new, optional): intent별 tool_required/timeout/retry 정책 버전 관리
- `contracts/` 변경이 필요하면 별도 PR로 분리

## Observability
- `chat_tool_route_total{intent,tool,status}`
- `chat_tool_latency_ms{tool}`
- `chat_tool_authz_denied_total{intent}`
- `chat_tool_schema_violation_total{tool}`
- `chat_tool_fallback_total{reason_code}`

## Test / Validation
- 정상: 주문/배송/환불 인텐트별 golden test
- 권한: 타인 주문번호 접근 100% 차단
- 장애: timeout/5xx/schema mismatch/fallback regression test
- 회귀: 일반 Q&A 질의에서 tool 오탐 호출률 상한 검증

## DoD
- 주문/배송/환불 질의의 tool 경로 성공률 지표 확보
- 권한 위반 케이스 100% 차단
- tool 실패 시 fallback 응답 표준화 및 reason_code 노출
- 일반 LLM 경로와 tool 경로가 로그/대시보드에서 분리 집계
- 한국어 템플릿 응답 스냅샷 테스트 통과

## Codex Prompt
Upgrade chat tool-calling for commerce intents:
- Add intent confidence gating and schema-validated tool I/O.
- Enforce per-user authorization context for all tool calls.
- Add timeout/retry/fallback behavior and deterministic Korean response templates.
- Emit full audit telemetry for tool route, failures, and auth denials.
