# I-0365 — Chat Unit Economics SLO + Cost-to-Resolve Optimizer

## Priority
- P0

## Dependencies
- I-0350, I-0363
- B-0395, B-0396

## Goal
책봇 실서비스 운영에서 품질을 유지하면서 해결 1건당 비용(cost-to-resolve)을 예측·통제하는 운영 체계를 구축한다.

## Scope
### 1) Unit economics SLO
- 핵심 지표: cost per resolved session, unresolved cost burn, tool cost mix, token cost mix
- intent별 목표 범위와 경보 임계치 정의
- 품질 하락 없이 비용만 최적화되는지 상호 제약 조건 정의

### 2) Cost optimizer policy
- 고비용 경로(과도한 재작성/툴 반복)를 탐지해 자동 정책 조정
- 저위험 질의는 경량 경로, 고위험 질의는 고신뢰 경로로 라우팅
- 예산 임계치 접근 시 단계형 절약 모드(soft clamp/hard clamp) 적용

### 3) Forecast + budget guard
- 주간/월간 트래픽 예측과 비용 예측을 연결
- 릴리스 계획 대비 비용 시뮬레이션 및 초과 위험 사전 경고
- 예산 초과 가능성이 높으면 배포 게이트에 경고/차단 신호 전달

### 4) FinOps observability
- 서비스/인텐트/버전 단위 원가 대시보드 제공
- 비용 급등 구간의 원인(모델, 툴, 실패 재시도) 자동 분해
- 비용-품질 트레이드오프 리포트 주간 발행

## Observability
- `chat_cost_per_resolved_session{intent}`
- `chat_unresolved_cost_burn_total{intent}`
- `chat_cost_guardrail_action_total{action}`
- `chat_cost_quality_tradeoff_index`

## DoD
- cost-to-resolve가 목표 범위에서 안정적으로 관리됨
- 품질 하락 없이 비용 최적화 정책이 검증됨
- 예산 초과 위험이 릴리스 전에 가시화되고 자동 경고됨

## Codex Prompt
Add FinOps-grade control for production chat:
- Define unit-economics SLOs tied to resolved outcomes.
- Optimize routing/policy by risk and cost under quality constraints.
- Connect forecasting and budget guardrails to release decisions.
