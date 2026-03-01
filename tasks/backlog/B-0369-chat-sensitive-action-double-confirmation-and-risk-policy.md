# B-0369 — Chat Sensitive Action Guard (이중 확인 + 리스크 정책)

## Priority
- P1

## Dependencies
- B-0359, B-0364, U-0142

## Goal
주문취소/환불/배송지변경 같은 민감 액션에서 오실행을 방지하기 위해 리스크 기반 이중 확인 정책을 도입한다.

## Scope
### 1) Risk classification
- 액션을 `LOW/MEDIUM/HIGH` 리스크로 분류
- 금전 영향, 상태 변경 불가역성, 사용자 이력 기반 위험도 반영

### 2) Two-step confirmation
- MEDIUM/HIGH는 2단계 확인 질문 필수
- 확인 토큰(one-time confirmation token) 기반 실행

### 3) Step-up auth (optional)
- 고위험 액션은 추가 인증(비밀번호/OTP/재로그인) 정책 연결
- 인증 실패 시 액션 차단 + 상담 전환

### 4) Undo window + audit
- 가능한 액션에는 짧은 취소 가능 윈도우 제공
- 액션 요청/확인/실행/취소 전 과정을 audit trail에 기록

## Observability
- `chat_sensitive_action_requested_total{action,risk}`
- `chat_sensitive_action_confirmed_total{action}`
- `chat_sensitive_action_blocked_total{reason}`
- `chat_sensitive_action_undo_total{action}`

## Test / Validation
- 리스크 등급별 확인 단계 강제 테스트
- 확인 토큰 위조/재사용 방지 테스트
- step-up auth 실패/timeout 회귀 테스트

## DoD
- 민감 액션 오실행률 감소
- 고위험 액션 무확인 실행 0건
- 민감 액션 감사추적(누가/언제/왜) 100% 확보

## Codex Prompt
Harden sensitive chat actions:
- Add risk-based two-step confirmation and optional step-up authentication.
- Require one-time confirmation tokens before execution.
- Provide undo window where applicable and persist full audit trails.
