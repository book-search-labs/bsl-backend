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

## Implementation Update (2026-03-03, Bundle 1)
- [x] Budget model gate 추가
  - `scripts/eval/chat_reasoning_budget_model.py`
  - request/token/step/tool budget 필드 존재성, limit 유효성, duplicate scope 검증
  - 민감 인텐트(`CANCEL_ORDER/REFUND_REQUEST/ADDRESS_CHANGE/PAYMENT_CHANGE`) 예산 커버리지 검증
  - gate 모드에서 정책 버전 누락/필드 누락/중복/stale evidence 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_reasoning_budget_model.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REASONING_BUDGET_MODEL=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Runtime enforcement gate 추가
  - `scripts/eval/chat_reasoning_budget_runtime_enforcement.py`
  - budget exceeded 이후 enforcement coverage/warning-before-abort/graceful abort/retry prompt 비율 검증
  - hard breach 및 unhandled exceed request를 게이트화
  - gate 모드에서 runtime stale evidence 포함 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_reasoning_budget_runtime_enforcement.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REASONING_BUDGET_RUNTIME_ENFORCEMENT=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Adaptive policy gate 추가
  - `scripts/eval/chat_reasoning_budget_adaptive_policy.py`
  - 비용/성공률 기반 동적 조정의 unsafe expansion, success/cost regression을 게이트화
  - 고비용 인텐트 preconfirm coverage/missing 추적
  - gate 모드에서 stale evidence 포함 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_reasoning_budget_adaptive_policy.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REASONING_BUDGET_ADAPTIVE_POLICY=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Audit explainability gate 추가
  - `scripts/eval/chat_reasoning_budget_audit_explainability.py`
  - reason_code/trace_id/request_id/budget_type/audit explain payload 누락 검증
  - dashboard 태그(intent/tenant) 누락을 게이트화
  - gate 모드에서 stale evidence 포함 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_reasoning_budget_audit_explainability.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REASONING_BUDGET_AUDIT_EXPLAINABILITY=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline governance 적용
  - `scripts/eval/chat_reasoning_budget_model.py`
  - `scripts/eval/chat_reasoning_budget_runtime_enforcement.py`
  - `scripts/eval/chat_reasoning_budget_adaptive_policy.py`
  - `scripts/eval/chat_reasoning_budget_audit_explainability.py`
  - 공통: `--baseline-report` + drift threshold 인자 + `gate.baseline_failures` + `source/derived.summary` 추가
- [x] baseline 회귀 테스트 추가
  - `scripts/eval/test_chat_reasoning_budget_model.py`
  - `scripts/eval/test_chat_reasoning_budget_runtime_enforcement.py`
  - `scripts/eval/test_chat_reasoning_budget_adaptive_policy.py`
  - `scripts/eval/test_chat_reasoning_budget_audit_explainability.py`
- [x] baseline fixture 추가
  - `services/query-service/tests/fixtures/chat_reasoning_budget_model_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_reasoning_budget_runtime_enforcement_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_reasoning_budget_adaptive_policy_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_reasoning_budget_audit_explainability_baseline_v1.json`
- [x] CI wiring + RUNBOOK 업데이트
  - `scripts/test.sh` reasoning budget 4개 gate에 baseline drift env/arg wiring 추가
  - `docs/RUNBOOK.md` B-0374 Bundle 1~4에 baseline drift gate 인자/환경변수 반영
