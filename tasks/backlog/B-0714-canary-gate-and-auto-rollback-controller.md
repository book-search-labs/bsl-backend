# B-0714 — Canary Gate + Auto Rollback Controller

## Priority
- P1

## Dependencies
- B-0713
- B-0712
- I-0352

## Goal
canary 배포에서 핵심 SLO 위반 시 자동 롤백하는 제어기를 구현해 리라이트 리스크를 운영 단계에서 제한한다.

## Scope
### 1) Canary gate rules
- 필수 게이트: 무확인 write 0건, authz 사고 0건, invalid reason_code ratio 0%
- 품질 게이트: 상태전이 pass rate, fallback ratio, shadow blocker diff ratio

### 2) Auto rollback logic
- 임계치 초과 시 `chat.force_legacy=true` 자동 적용
- cooldown window 내 반복 승격/롤백 플래핑 방지

### 3) Rollout stages
- `shadow(0%) -> canary(5%) -> step-up(10/25/50/100%)`
- 단계별 dwell time 및 승격 조건 문서화

### 4) Audit + runbook
- 롤백 이벤트 감사로그(사유/수치/시점) 기록
- 온콜 대응 런북 절차 포함

## Test / Validation
- gate simulation tests
- threshold breach auto rollback tests
- cooldown and re-entry tests

## DoD
- 게이트 위반 시 자동 rollback이 동작한다.
- 롤백 사유가 trace/audit에 남는다.
- 단계별 승격/차단 기준이 문서화되어 운영자가 재현 가능하다.

## Codex Prompt
Build canary gate with automatic rollback:
- Enforce hard safety SLOs before promotion.
- Auto-enable force-legacy on threshold breach.
- Record rollback rationale and metrics for audit.
