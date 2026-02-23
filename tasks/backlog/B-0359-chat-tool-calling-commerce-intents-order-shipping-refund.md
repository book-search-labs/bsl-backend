# B-0359 — Chat Tool Calling v3 (주문/배송/환불 인텐트 연동 고도화)

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

### 6) Multi-tool orchestration for real service (신규)
- 단일 질의에서 복수 tool 호출을 지원:
  - 주문 상태 조회 → 배송 상태 조회 → 환불 가능 여부 산출
- tool 호출 순서/의존성을 워크플로우로 명시하고 partial failure 시 단계별 fallback
- 상태 불일치(예: 주문 취소인데 배송 완료 응답) 검출 시 안전 중단 + 운영 티켓 자동 생성(옵션)

### 7) SLA and completion contract (신규)
- 커머스 인텐트 SLA:
  - p95 응답시간 <= 2.5s (tool timeout 제외)
  - tool 성공률 >= 99%
- task completion 정의:
  - 사용자 질의 목적(조회/정책안내/다음행동 제시)이 충족되었을 때만 success 집계
- completion 실패는 reason_code와 함께 평가 파이프라인으로 전송

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
- `chat_tool_completion_total{intent,completed}`
- `chat_tool_sla_breach_total{intent}`

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
- 복수 tool 오케스트레이션 시나리오(주문→배송→환불) 회귀 테스트 통과
- completion/SLA 지표가 운영 대시보드에서 실시간 확인 가능

## Codex Prompt
Upgrade chat tool-calling for commerce intents:
- Add intent confidence gating and schema-validated tool I/O.
- Enforce per-user authorization context for all tool calls.
- Add timeout/retry/fallback behavior and deterministic Korean response templates.
- Emit full audit telemetry for tool route, failures, and auth denials.

## Implementation Update (2026-02-23, Bundle 4)
- [x] 상담 전환 흐름 강화
  - `chat:unresolved:{session_id}` 캐시에 직전 실패 질의/사유(`reason_code`) 저장
  - 사용자가 `문의 접수해줘`처럼 짧게 입력해도 직전 실패 컨텍스트를 티켓 payload에 자동 첨부
- [x] 티켓 생성 payload 보강
  - `details.effectiveQuery`, `details.unresolvedReasonCode`, `details.unresolvedTraceId`, `details.unresolvedRequestId` 추가
  - 접수 완료 메시지에 직전 실패 사유 전달 여부를 명시
- [x] 메트릭 추가
  - `chat_ticket_create_with_context_total{source}`
- [x] 테스트 추가
  - generic 문의 문구에서 unresolved context를 활용해 티켓 생성하는 회귀 테스트 추가
