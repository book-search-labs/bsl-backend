# B-0374 — Chat Reasoning Budget Controller (step/token/tool limits)

## Priority
- P2

## Dependencies
- I-0350, B-0367, I-0353

## Goal
에이전트형 챗 실행에서 무한 루프/과도한 tool 호출/비용 폭증을 방지하기 위해 reasoning budget 제어기를 도입한다.

## Scope
### 1) Budget model
- request별 token budget, step budget, tool_call budget 정의
- 사용자/테넌트/인텐트별 차등 한도 설정

### 2) Runtime enforcement
- 한도 초과 전 조기 경고 및 축약 전략 적용
- 초과 시 안전 중단 + 재질문 유도

### 3) Adaptive policy
- 성공률/비용 기반 동적 budget 튜닝(보수적 시작)
- 고비용 인텐트에 사전 확인 단계 삽입

### 4) Audit and explainability
- budget 소진 원인(reason_code) 로그
- 운영자 대시보드에 budget 소비 패턴 제공

## Observability
- `chat_budget_exceeded_total{budget_type}`
- `chat_budget_consumed_ratio{budget_type}`
- `chat_budget_adaptive_adjust_total{policy}`
- `chat_budget_abort_total{reason}`

## Test / Validation
- step/token/tool 초과 시나리오 테스트
- 조기 중단 후 재시도 UX 회귀 테스트
- budget 정책 변경 전/후 비용 비교 리포트

## DoD
- budget 초과로 인한 장애/비용 급증 케이스 감소
- 조기중단 응답의 사용자 이해가능성 확보
- budget 정책 효과를 지표로 검증 가능

## Codex Prompt
Implement reasoning budget controls for chat agents:
- Enforce per-request limits on tokens, steps, and tool calls.
- Apply graceful early-stop strategies before hard budget breach.
- Track budget behavior and adaptive tuning outcomes with telemetry.
