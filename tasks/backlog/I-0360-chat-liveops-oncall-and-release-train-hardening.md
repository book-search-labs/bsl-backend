# I-0360 — Chat LiveOps 강화 (온콜 안전망 + 릴리스 트레인)

## Priority
- P0

## Dependencies
- I-0351, I-0352, I-0353, I-0354, I-0355, I-0356
- B-0391, A-0150

## Goal
책봇 실서비스 운영 중 장애/비용/품질 리스크를 자동 감지하고, 릴리스 트레인 기반으로 안전하게 배포/롤백할 수 있는 인프라 운영체계를 완성한다.

## Scope
### 1) Release train and rollout guard
- 정시 릴리스 트레인(주간/긴급) 정책 수립
- canary/shadow 트래픽 승격 조건 자동화
- 컷라인 위반 시 즉시 fail-closed + 자동 rollback

### 2) On-call safety net
- 주요 알람(groundedness 급락, tool timeout 급증, 비용 급등) 룰 강화
- 알람→런북→조치→검증 자동 연결
- P1/P0 장애의 MTTA/MTTR 자동 집계

### 3) Capacity and cost resilience
- 모델/툴별 토큰/요청/비용 예산 캡
- 과부하 시 우선순위 큐 + load shedding + fallback 단계화
- 장애 중에도 핵심 커머스 의도는 우선 보존

### 4) Recovery and trust
- 재시작 후 세션 복구 무결성 점검
- 구성 드리프트 탐지 + immutable bundle 강제
- DR drill 정례화 및 결과 리포트 자동 저장

## DoD
- 릴리스 승격/차단/롤백이 자동 정책으로 동작
- 온콜 운영 지표(MTTA/MTTR/SLO) 안정화
- 비용 폭주/과부하 상황에서도 핵심 사용자 시나리오 유지
- 월간 DR 리허설 리포트 누적

## Codex Prompt
Harden chat live operations for production:
- Enforce release train gating with automatic rollback on gate breach.
- Build on-call automation from alert to runbook to validation.
- Add capacity/cost guardrails with priority-based degradation.
- Validate recovery integrity and immutable config bundle discipline.
