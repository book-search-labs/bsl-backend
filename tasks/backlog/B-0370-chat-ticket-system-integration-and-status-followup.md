# B-0370 — Chat Ticket Integration (접수/상태추적/후속안내)

## Priority
- P2

## Dependencies
- U-0143, B-0363, B-0359

## Goal
챗봇에서 해결 불가한 이슈를 지원 티켓으로 연계하고, 접수 이후 상태 변화를 챗 세션에서 추적 가능하게 만든다.

## Scope
### 1) Ticket creation API integration
- 챗 대화에서 티켓 생성 payload 표준화(요약/주문정보/오류코드)
- 접수번호/예상 처리시간 반환

### 2) Status sync
- 티켓 상태(`RECEIVED/IN_PROGRESS/WAITING_USER/RESOLVED/CLOSED`) 조회 API 연동
- 챗에서 "내 문의 상태" 질의 시 최신 상태 응답

### 3) Follow-up prompts
- 상태 전이에 따라 필요한 사용자 액션 가이드(자료 추가/확인 요청) 제공
- 장시간 미응답 티켓에 대한 리마인드 정책

### 4) Security and ownership
- 사용자 본인 티켓만 조회
- 개인정보/첨부파일 링크 마스킹

## Observability
- `chat_ticket_created_total{category}`
- `chat_ticket_status_lookup_total{result}`
- `chat_ticket_followup_prompt_total{status}`
- `chat_ticket_authz_denied_total`

## Test / Validation
- 티켓 생성/조회 e2e
- 타인 티켓 조회 차단 테스트
- 상태 전이별 후속 프롬프트 회귀 테스트

## DoD
- 챗에서 티켓 접수 및 상태조회가 end-to-end 동작
- 티켓 연계 후 사용자 이탈률 감소
- 티켓 상태 불일치/오조회 이슈 감소

## Codex Prompt
Integrate chat with support tickets:
- Create tickets from unresolved chat sessions with structured context.
- Expose secure ticket status lookups and follow-up guidance in chat.
- Enforce ownership checks and ticket lifecycle observability.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Ticket creation integration gate 추가
  - `scripts/eval/chat_ticket_creation_integration.py`
  - ticket 생성 요청 payload의 필수 컨텍스트(summary/order/error_code) 누락을 집계
  - 생성 성공 응답의 접수번호(`ticket_no`)와 예상 처리시간(`eta`) 누락을 게이트화
  - gate 모드에서 생성 성공률 저하, payload 누락, 접수 응답 누락, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_ticket_creation_integration.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TICKET_CREATION_INTEGRATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Ticket status sync gate 추가
  - `scripts/eval/chat_ticket_status_sync.py`
  - 상태 조회 결과(ok/not_found/forbidden/error)와 상태값 유효성(`RECEIVED/IN_PROGRESS/WAITING_USER/RESOLVED/CLOSED`)을 검증
  - 최신 상태 timestamp 기준 stale status 및 ticket reference 누락을 게이트화
  - gate 모드에서 조회 성공률 저하, invalid status, reference 누락, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_ticket_status_sync.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TICKET_STATUS_SYNC=1 ./scripts/test.sh`
