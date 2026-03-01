# I-0352 — Chat Canary + Shadow Traffic + 자동 롤백 게이트 (운영 고도화)

## Priority
- P1

## Dependencies
- B-0357 (품질 게이트)
- A-0140 (지표 관측)
- A-0141 (정책/프롬프트 버전 관리)

## Goal
챗봇 모델/프롬프트/정책 배포를 shadow + canary로 보호하고, 품질/비용/오류 회귀 시 자동 롤백한다.

## Scope
### 1) Shadow traffic
- 실사용 질의를 신규 버전에 비노출 복제
- 기존 버전 대비 응답 품질/지연/비용 diff 계산
- 개인정보 포함 payload는 마스킹 후 shadow로 전달

### 2) Canary rollout
- 단계: 1% → 5% → 20% → 50% → 100%
- 단계별 검증 윈도우(예: 15~30분)
- 단계 전환은 자동/수동 승인 모드 모두 지원

### 3) Gate criteria
- error rate, timeout rate, hallucination rate, groundedness, cost burn rate
- 임계치 초과 시 다음 단계 진입 차단
- 필수 게이트 예시:
  - `error_rate <= 1.5x baseline`
  - `p95_latency <= 1.3x baseline`
  - `grounded_response_rate >= baseline - 2%p`
  - `cost_per_1k <= baseline + 15%`

### 4) Auto rollback
- 2회 연속 윈도우 실패 시 즉시 이전 안정 버전 복귀
- 롤백 이벤트 감사 로그 기록
- 롤백 후 최소 30분 재진입 금지 cooldown

### 5) Release evidence
- 배포마다 canary 리포트 아티팩트 저장
- 승인자/버전/결정 근거 기록
- 리포트에는 샘플 실패 케이스와 주요 reason_code 포함

## Non-goals
- 모델 자체 학습 파이프라인 구축은 범위 외
- 신규 APM 도구 도입은 필수 아님(기존 스택 우선)

## Observability
- `chat_canary_stage{version,stage,status}`
- `chat_canary_gate_breach_total{metric,version}`
- `chat_auto_rollback_total{reason,version}`
- `chat_shadow_diff_score{metric,version}`

## Runbook integration
- 게이트 실패 유형별 대응 경로를 `docs/RUNBOOK.md`에 연결
- 자동 롤백 후 온콜 알림(슬랙/이메일) + 후속 RCA 티켓 자동 생성(옵션)

## DoD
- canary 중 회귀 시 자동 롤백 동작 검증
- shadow/canary 결과를 대시보드와 리포트에서 확인 가능
- 운영자가 배포 결정 근거를 감사 로그로 추적 가능
- 2회 이상 실제 릴리즈에서 canary evidence artifact 생성 확인

## Codex Prompt
Harden chat canary/shadow rollout:
- Run non-user-visible shadow evaluation before canary.
- Enforce staged gates on reliability, quality, and cost metrics.
- Auto-rollback on threshold breaches and persist release evidence.
