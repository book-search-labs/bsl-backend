# B-0389 — Chat Tool Health Score + Capability Routing

## Priority
- P1

## Dependencies
- B-0364, B-0359, I-0354

## Goal
도구(tool)별 건강상태와 지원능력(capability)을 점수화해, 장애/성능저하 상황에서 더 안전한 도구로 자동 라우팅한다.

## Scope
### 1) Tool health scoring
- 성공률/지연/에러유형/최근 변동성 기반 health score 산출
- capability 매트릭스(지원 인텐트/필수 파라미터) 관리

### 2) Capability routing
- 인텐트별 후보 tool 선택 시 health + capability 동시 반영
- 기준 미달 tool 자동 제외

### 3) Degrade strategy
- 주도구 실패 시 대체 tool 순차 시도
- 대체 불가 시 안전 fallback/티켓 전환

### 4) Operator overrides
- 운영자가 특정 tool 강제 제외/우선 사용 설정
- override 이력 감사 로그

## Observability
- `chat_tool_health_score{tool}`
- `chat_tool_capability_route_total{intent,tool,result}`
- `chat_tool_capability_miss_total{intent}`
- `chat_tool_override_applied_total{tool}`

## Test / Validation
- tool 장애 주입 시 라우팅 전환 테스트
- capability 미스매치 차단 테스트
- override 적용/해제 회귀 테스트

## DoD
- 장애 시 잘못된 tool 호출 감소
- 대체 라우팅 성공률 개선
- tool 건강도/능력 기반 의사결정 추적 가능

## Codex Prompt
Add capability-aware tool routing for chat:
- Score tool health from reliability and latency signals.
- Route intents to tools that satisfy capability and health thresholds.
- Support safe degradation and operator overrides with full telemetry.

## Implementation Update (2026-03-04, Bundle 1)
- [x] Tool health score guard gate 추가
  - `scripts/eval/chat_tool_health_score_guard.py`
  - 성공률/지연/오류/변동성 기반 health score 산출 및 임계 검증
  - unhealthy tool 총량 및 telemetry 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_health_score_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_HEALTH_SCORE_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 2)
- [x] Tool capability routing guard gate 추가
  - `scripts/eval/chat_tool_capability_routing_guard.py`
  - capability match ratio 및 capability miss 차단 검증
  - below-health tool 라우팅 및 no-candidate 총량 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_capability_routing_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_CAPABILITY_ROUTING_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 3)
- [x] Tool degrade strategy guard gate 추가
  - `scripts/eval/chat_tool_degrade_strategy_guard.py`
  - 주도구 실패 시 fallback 시도 coverage 및 safe fallback 이행률 검증
  - stalled degrade 및 duplicate-tool retry 위반 건수 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_tool_degrade_strategy_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TOOL_DEGRADE_STRATEGY_GUARD=1 ./scripts/test.sh`
