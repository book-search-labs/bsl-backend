# I-0353 — Chat SLO Guardrails + Auto Remediation (개정 v2)

## Priority
- P1

## Dependencies
- I-0303, I-0352
- I-0316 (Runbook / On-call)
- I-0363 (capacity forecasting)

## Goal
챗봇 SLO를 명확히 정의하고, 위반 시 자동 완화(degrade/throttle/rollback)를 수행한다.

## Non-goals
- 신규 모니터링 벤더 전환은 필수로 포함하지 않는다.
- 모델 품질 자체 개선(학습) 작업은 이 티켓 범위가 아니다.

## Scope
### 1) SLO 정의
- availability, p95 latency, error rate, grounded response rate
- 예시 초기목표:
  - availability >= 99.5%
  - p95 latency <= 2.5s
  - error_rate <= 1.0%
  - grounded_response_rate >= 92%

### 2) Alert policy
- burn-rate alert, multi-window/multi-burn-rate
- fast burn (5m/30m), slow burn (1h/6h) 조합 적용

### 3) Auto remediation
- latency 급등 시 rerank disable
- error 급등 시 tool-only mode
- 품질 회귀 시 canary rollback
- 비용 급등 시 request budget clamp + low-priority traffic throttle
- 연속 위반 시 단계형 remediation escalation

### 4) Runbook linkage
- 자동 조치 발생 시 런북 절차 링크 및 알림
- 조치 성공/실패 결과를 incident timeline에 자동 기록

### 5) Degradation ladder + auto-unwind (신규)
- 완화 단계 표준화: `NORMAL -> SOFT_DEGRADE -> HARD_DEGRADE -> ISOLATION`
- 단계 진입/해제에 hysteresis(진입 임계치와 해제 임계치 분리) 적용
- 지표 회복 시 자동 복귀(auto-unwind)하되, 급격한 왕복(flapping) 방지

## Observability
- `chat_slo_violation_total{slo,window}`
- `chat_auto_remediation_total{action,result}`
- `chat_remediation_duration_ms{action}`
- `chat_slo_error_budget_remaining{window}`
- `chat_degrade_level_current`
- `chat_auto_unwind_total{from,to,result}`

## Test / Validation
- fault injection으로 latency/error/cost/groundedness 위반 재현
- remediation chain 동작 순서 검증 (degrade -> throttle -> rollback)
- false positive/false negative 비율 검증
- 런북 링크/알림 payload 정확성 검증

## DoD
- SLO 위반 상황에서 자동 완화 동작 검증
- 조치 전/후 지표 차이 리포트 생성
- 온콜이 5분 내 위반 원인과 자동조치 상태를 식별 가능
- 재발 방지 액션(티켓/회고) 자동 생성 또는 링크 보장
- degrade 단계 전환/복귀 이력이 감사 가능하게 남음

## Codex Prompt
Add chat SLO guardrails with auto-remediation:
- Define chat SLOs and burn-rate alerts.
- Trigger policy-based remediation actions on violations.
- Link actions to incident runbook and reporting.
- Add staged escalation and measurable action effectiveness tracking.

## Implementation Update (2026-02-23, Bundle 11)
- [x] timeout observability 보강
  - `chat_timeout_total{stage}` 메트릭 추가
  - stage 구분: `llm_generate`, `llm_stream`, `tool_lookup`
- [x] 적용 경로
  - LLM non-stream timeout fallback
  - LLM stream timeout fallback
  - Tool lookup timeout fallback
- [x] 회귀 테스트 추가
  - LLM timeout 시 `chat_timeout_total{stage=llm_generate}` 증가 검증
  - Tool timeout 시 `chat_timeout_total{stage=tool_lookup}` 증가 검증
