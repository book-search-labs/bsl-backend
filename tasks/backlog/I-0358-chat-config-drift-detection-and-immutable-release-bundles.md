# I-0358 — Chat Config Drift Detection + Immutable Release Bundles

## Priority
- P1

## Dependencies
- I-0352, I-0357, B-0386

## Goal
환경 간 설정 드리프트로 인한 챗봇 품질/안전성 회귀를 방지하기 위해 불변 릴리즈 번들과 드리프트 탐지를 도입한다.

## Non-goals
- 완전 무중단 배포 전략 자체를 새로 도입하지 않는다.
- 어플리케이션 외부 시스템 전체 설정을 본 티켓에서 통합관리하지 않는다.

## Scope
### 1) Immutable bundles
- 모델/프롬프트/정책/툴설정/feature-flag를 단일 릴리즈 번들로 고정
- 번들 해시 기반 배포/롤백

### 2) Drift detection
- 런타임 설정을 기준 번들과 주기 비교
- 불일치 탐지 시 알림 + 자동 복원(옵션)

### 3) Environment parity checks
- dev/stage/prod 설정 차이 리포트 자동 생성
- 허용된 차이(allowlist)만 예외 처리

### 4) Governance and safety
- 릴리즈 승인 전 drift clean 상태 강제
- drift incident 감사로그 및 RCA 링크 저장

## Runbook integration
- drift 탐지 시 운영자 조치 단계(runbook) 링크 제공
- 자동 복원 실패 시 canary rollback 연계 절차 문서화

## Observability
- `chat_release_bundle_applied_total{env,result}`
- `chat_config_drift_detected_total{env,type}`
- `chat_config_drift_auto_remediate_total{result}`
- `chat_env_parity_violation_total{env}`
- `chat_release_bundle_checksum_mismatch_total{env}`

## Test / Validation
- 의도적 drift 주입/탐지 테스트
- 번들 롤백 무결성 테스트
- allowlist 정책 회귀 테스트
- drift 반복 발생 시 알림 dedup/노이즈 제어 테스트

## DoD
- 환경 드리프트 조기 탐지 체계 확보
- 불변 번들 기반 릴리즈 재현성 확보
- drift 사고의 추적/복구 절차 자동화
- 운영자가 5분 내 drift 원인 범주 식별 가능

## Codex Prompt
Harden chat release consistency:
- Ship immutable release bundles for prompts/policies/models/config.
- Detect runtime drift against expected bundle state and alert/remediate.
- Enforce environment parity checks before promotion.
