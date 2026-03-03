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

## Implementation Update (2026-03-03, Bundle 1)
- [x] Sensitive action risk classification gate 추가
  - `scripts/eval/chat_sensitive_action_risk_classification.py`
  - 민감 액션 이벤트를 `LOW/MEDIUM/HIGH` 리스크로 집계하고 unknown risk 유입을 차단
  - HIGH 리스크에서 step-up auth 요구 누락 건수, irreversible 액션의 HIGH 미분류 건수를 게이트화
  - actor/target 감사 필드 누락 및 stale evidence 위반을 운영 차단 조건으로 추가
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_sensitive_action_risk_classification.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SENSITIVE_ACTION_RISK_CLASSIFICATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Two-step confirmation + one-time token gate 추가
  - `scripts/eval/chat_sensitive_action_double_confirmation.py`
  - MEDIUM/HIGH 리스크 액션에서 step1/step2 확인 누락 실행(`execute_without_double_confirmation_total`)을 검출
  - confirmation token 발급/검증/재사용/불일치/만료 이벤트를 집계해 token 재사용·오용을 게이트화
  - gate 모드에서 무이중확인 실행, token 미검증 실행, token replay/mismatch/expiry, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_sensitive_action_double_confirmation.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SENSITIVE_ACTION_DOUBLE_CONFIRMATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Step-up auth 정책 게이트 추가
  - `scripts/eval/chat_sensitive_action_stepup_auth.py`
  - HIGH 리스크 액션에서 step-up 인증 완료 전 실행(`high_risk_execute_without_stepup_total`)을 검출
  - step-up 실패/타임아웃 이후 block 또는 handoff로 전환되지 않은 실행 지속을 차단
  - gate 모드에서 고위험 무인증 실행, 실패 후 실행 지속, failure block ratio 저하, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_sensitive_action_stepup_auth.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SENSITIVE_ACTION_STEPUP_AUTH=1 ./scripts/test.sh`
