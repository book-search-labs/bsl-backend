# B-0712 — OpenFeature Engine Routing + Kill Switch

## Priority
- P1

## Dependencies
- B-0703

## Goal
엔진 라우팅(`legacy/shadow/canary/agent`)을 OpenFeature로 표준화하고, 장애 시 즉시 legacy로 강제 전환 가능한 kill switch를 제공한다.

## Scope
### 1) OpenFeature provider integration
- query-service에서 OpenFeature client 도입
- flag 키: `chat.engine.mode`, `chat.langgraph.enabled`, `chat.force_legacy`

### 2) Evaluation context
- context 필드: `tenant_id`, `user_id`, `session_id`, `channel`, `risk_band`
- high-risk 요청에서 안전한 기본값(legacy 우선) 적용

### 3) Runtime routing
- flag 값에 따라 엔진 선택
- shadow 모드에서 응답은 legacy, graph는 백그라운드 비교 실행

### 4) Kill switch + audit
- 강제 legacy 전환 시 audit append
- 전환 시점/사유/범위를 운영 로그에 남김

## Test / Validation
- feature flag routing matrix tests
- context-based evaluation tests
- force-legacy kill switch tests

## DoD
- 운영자가 코드 배포 없이 엔진 라우팅을 제어할 수 있다.
- kill switch 실행 시 1분 내 legacy 강제 전환된다.
- 라우팅 변경 이력이 감사 가능하다.

## Codex Prompt
Adopt OpenFeature for chat engine routing:
- Evaluate flags with tenant/user/session context.
- Route among legacy/shadow/canary/agent modes.
- Implement audited force-legacy kill switch.
