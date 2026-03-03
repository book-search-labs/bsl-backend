# I-0366 — Chat Policy Distribution + Realtime Config Control Plane

## Priority
- P0

## Dependencies
- I-0358, I-0364, I-0365
- B-0371, B-0397

## Goal
책봇 정책/프롬프트/라우팅 설정을 실시간으로 안전 배포하고, 장애 시 즉시 이전 안정 버전으로 복귀 가능한 제어면(control plane)을 구축한다.

## Scope
### 1) Realtime config distribution
- 정책 번들(프롬프트/룰/임계치/라우팅) 서명된 아티팩트로 배포
- 서비스 인스턴스별 적용 버전과 드리프트 상태 추적
- 단계적 롤아웃(1% -> 10% -> 50% -> 100%) 자동화

### 2) Safety guards
- 배포 전 정합성 검사(schema, dependency, forbidden setting)
- 배포 중 SLO/품질/비용 이상 감지 시 자동 중단 + 롤백
- emergency kill switch로 특정 정책/기능 즉시 비활성화

### 3) Audit and reproducibility
- "누가 언제 어떤 설정을 배포했는지" immutable audit log 기록
- 시점별 설정 스냅샷 재현(incident replay) 지원
- 릴리스 단위 변경 diff/영향 범위 리포트 제공

### 4) Ops runbook integration
- 실패 유형별 자동 대응 플레이북 연결
- 온콜 알림 payload에 배포 버전/영향 서비스/권장 조치 포함

## Observability
- `chat_config_rollout_total{bundle,result}`
- `chat_config_drift_total{service}`
- `chat_config_auto_rollback_total{reason}`
- `chat_config_killswitch_total{scope}`

## DoD
- 정책 배포/롤백이 무중단으로 동작하고 재현 가능
- 설정 이상으로 인한 장애 전파가 자동 차단됨
- 감사/사고 대응에 필요한 배포 증적이 완전하게 남음

## Codex Prompt
Build a realtime control plane for chat policy/config rollout:
- Distribute signed config bundles with staged rollout and drift tracking.
- Add guardrails, auto-stop, and rollback on quality/SLO/cost anomalies.
- Preserve immutable audit trails and reproducible config snapshots.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Realtime config distribution rollout gate 추가
  - `scripts/eval/chat_config_distribution_rollout.py`
  - 배포 이벤트(`bundle/stage/result/signature_valid/desired_version/applied_version`)를 집계해 success ratio, signature 위반, stage regression, drift ratio를 계산
  - bundle별 required stage(1/10/50/100) 누락 여부와 서비스별 drift 분포를 리포팅
  - gate 모드에서 success 저하, drift 증가, 서명 위반, stage regression, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_config_distribution_rollout.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CONFIG_DISTRIBUTION_ROLLOUT=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Config safety guard gate 추가
  - `scripts/eval/chat_config_safety_guard.py`
  - anomaly(slo/quality/cost breach) 이벤트에서 auto-stop/rollback/killswitch 대응 집계
  - unhandled anomaly, mitigation ratio, detection lag p95, forbidden kill-switch scope 위반을 계산
  - gate 모드에서 대응 누락/탐지 지연/금지 scope 위반/stale evidence를 차단
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_config_safety_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CONFIG_SAFETY_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Config audit reproducibility gate 추가
  - `scripts/eval/chat_config_audit_reproducibility.py`
  - config audit 이벤트에서 actor/request/trace 누락, immutable 위반, snapshot replay 가능 여부, diff 증적 커버리지를 집계
  - snapshot id/path 기반 재현 가능률(`snapshot_replay_ratio`)과 변경 diff 증적 비율(`diff_coverage_ratio`)을 게이트화
  - stale evidence, 감사 필드 누락, immutable 위반 시 배포 증적 불충분으로 차단
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_config_audit_reproducibility.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CONFIG_AUDIT_REPRO_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Config ops runbook integration gate 추가
  - `scripts/eval/chat_config_ops_runbook_integration.py`
  - incident 이벤트에서 runbook/recommended action/bundle version/impacted services 포함 여부를 점검
  - payload 완전성 비율(`payload_complete_ratio`)과 필수 필드 누락 건수를 운영 게이트로 검증
  - stale evidence 및 알림 payload 미완전 사례를 배포 차단 조건으로 명시
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_config_ops_runbook_integration.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CONFIG_OPS_RUNBOOK_INTEGRATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline drift governance 추가 (I-0366 전체)
  - `scripts/eval/chat_config_distribution_rollout.py`
  - `scripts/eval/chat_config_safety_guard.py`
  - `scripts/eval/chat_config_audit_reproducibility.py`
  - `scripts/eval/chat_config_ops_runbook_integration.py`
  - 공통으로 `--baseline-report` + drift threshold 인자를 지원하고, `gate.pass`를 `failures + baseline_failures` 결합 기준으로 계산
  - payload에 `source`, `derived.summary`를 추가해 baseline 비교 입력 스키마를 고정
- [x] Baseline 회귀 단위테스트 추가
  - `scripts/eval/test_chat_config_distribution_rollout.py`
  - `scripts/eval/test_chat_config_safety_guard.py`
  - `scripts/eval/test_chat_config_audit_reproducibility.py`
  - `scripts/eval/test_chat_config_ops_runbook_integration.py`
- [x] CI baseline wiring 추가
  - `scripts/test.sh` 40~43단계에 baseline fixture 자동 연결 + drift env 노출
- [x] Baseline fixture 추가
  - `services/query-service/tests/fixtures/chat_config_distribution_rollout_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_config_safety_guard_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_config_audit_reproducibility_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_config_ops_runbook_integration_baseline_v1.json`
