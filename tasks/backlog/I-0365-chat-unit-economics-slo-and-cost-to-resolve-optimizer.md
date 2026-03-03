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

## Implementation Update (2026-03-03, Bundle 1)
- [x] Unit economics SLO gate 추가
  - `scripts/eval/chat_unit_economics_slo.py`
  - 세션 비용 이벤트(`resolved/session_cost_usd/tool_cost_usd/token_cost_usd/intent`)를 집계해 `cost_per_resolved_session`, `unresolved_cost_burn_total`, tool/token mix, resolution rate를 계산
  - gate 모드에서 resolution rate 하락, cost-per-resolve 초과, unresolved burn 초과, tool mix 과다, stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_unit_economics_slo.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_UNIT_ECONOMICS_SLO=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Cost optimizer policy gate 추가
  - `scripts/eval/chat_cost_optimizer_policy.py`
  - 세션 비용 이벤트를 기반으로 budget utilization(`soft/hard`)을 해석해 `NORMAL/SOFT_CLAMP/HARD_CLAMP` 모드 결정
  - intent별 risk/resolution/cost를 반영해 route policy(`TRUSTED/BALANCED/LIGHT`)와 action reason을 계산
  - 고위험 intent light 강등/저품질 intent light 라우팅/하드클램프 미적용 같은 운영 사고를 gate에서 차단
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_cost_optimizer_policy.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_COST_OPTIMIZER_POLICY=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Budget release guard gate 추가
  - `scripts/eval/chat_budget_release_guard.py`
  - `chat_capacity_forecast + chat_unit_economics_slo + chat_cost_optimizer_policy` 최신 리포트를 결합해 release guard 계산
  - post-optimizer budget utilization, resolution rate, unresolved burn, cost-per-resolved 기준으로 `PROMOTE/HOLD/BLOCK` 상태 판정
  - budget 압력이 높은데 clamp가 빠진 구성(require-clamp)도 운영 실패로 차단
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_budget_release_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_BUDGET_RELEASE_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] FinOps tradeoff report gate 추가
  - `scripts/eval/chat_finops_tradeoff_report.py`
  - `chat_unit_economics_slo`/`chat_budget_release_guard` 리포트를 집계해 평균 cost-per-resolved, resolution, unresolved burn, budget utilization, tradeoff index를 계산
  - `var/llm_gateway/audit.log` reason_code를 비용 기준으로 분해해 급등 원인(top reasons) 가시화
  - 비용은 줄었지만 품질이 함께 하락한 회귀(`quality_drop_with_cost_cut`)를 gate에서 차단
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_finops_tradeoff_report.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_FINOPS_TRADEOFF_REPORT=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline drift governance 추가 (I-0365 전체)
  - `scripts/eval/chat_unit_economics_slo.py`
  - `scripts/eval/chat_cost_optimizer_policy.py`
  - `scripts/eval/chat_budget_release_guard.py`
  - `scripts/eval/chat_finops_tradeoff_report.py`
  - 공통으로 `--baseline-report` + drift threshold 인자를 지원하고, `gate.pass`를 `failures + baseline_failures` 결합 기준으로 계산
  - payload에 `source`, `derived.summary`를 추가해 baseline 비교 입력 스키마를 고정
- [x] Baseline 회귀 단위테스트 추가
  - `scripts/eval/test_chat_unit_economics_slo.py`
  - `scripts/eval/test_chat_cost_optimizer_policy.py`
  - `scripts/eval/test_chat_budget_release_guard.py`
  - `scripts/eval/test_chat_finops_tradeoff_report.py`
- [x] CI baseline wiring 추가
  - `scripts/test.sh` 36~39단계에 baseline fixture 자동 연결 + drift env 노출
- [x] Baseline fixture 추가
  - `services/query-service/tests/fixtures/chat_unit_economics_slo_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_cost_optimizer_policy_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_budget_release_guard_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_finops_tradeoff_report_baseline_v1.json`
