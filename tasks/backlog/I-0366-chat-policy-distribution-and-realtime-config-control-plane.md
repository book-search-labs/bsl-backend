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
