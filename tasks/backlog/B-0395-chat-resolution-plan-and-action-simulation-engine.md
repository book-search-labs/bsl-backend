# B-0395 — Chat Resolution Plan + Action Simulation Engine

## Priority
- P0

## Dependencies
- B-0359, B-0392, B-0393
- B-0394, I-0353

## Goal
책봇이 단순 안내를 넘어 "실행 가능한 해결 계획"을 생성해 주문/배송/환불 문의를 실제 완료까지 이끈다.

## Scope
### 1) Resolution plan compiler
- 다중 tool 결과를 `현재상태 -> 선택가능 액션 -> 예상결과` 구조로 표준화
- 주문/배송/반품/환불 reason_code별로 필수 확인 항목(주문번호, 수령여부, 기간 등) 강제
- 근거 부족 항목은 플랜 생성에서 제외하고 추가 확인 질문으로 전환

### 2) Action simulation
- 환불 예상금액(수수료/배송비/포인트 차감) 사전 시뮬레이션
- 배송 옵션(기본/빠른) 변경 시 비용/도착예정 비교 시뮬레이션
- 정책상 불가 시나리오는 즉시 차단하고 대체 경로(부분환불/교환/상담) 제시

### 3) Execution safety contract
- 실행 전 preflight 검증(권한/재고/상태 전이 가능 여부)
- 시뮬레이션 결과와 실제 실행 결과 불일치 시 자동 중단 + 운영 알림
- 액션별 idempotency key 강제 및 재실행 안전성 보장

### 4) Plan persistence and resume
- 세션 재진입 시 마지막 해결 플랜/진행 단계 복원
- 실패 단계부터 resume 가능한 checkpoint 저장
- 티켓 전환 시 요약 플랜을 운영자에게 전달

## Observability
- `chat_resolution_plan_created_total{intent}`
- `chat_action_simulation_total{action,result}`
- `chat_action_preflight_block_total{reason_code}`
- `chat_resolution_completion_total{intent,result}`

## Test / Validation
- 주문 상태별(결제대기/배송중/배송완료/취소) 플랜 생성 회귀 테스트
- 시뮬레이션-실행 결과 편차 검증 테스트
- 권한 위반/상태 불일치/중복 실행 장애 시나리오 검증

## DoD
- 커머스 문의에서 "다음에 무엇을 해야 하는지"가 명확한 플랜으로 제시됨
- 시뮬레이션 기반 안내와 실제 실행 결과 편차가 운영 기준 내로 유지됨
- 실패 시 안전 중단 + 재시도/상담 전환이 일관되게 동작함

## Codex Prompt
Implement a production chat resolution engine:
- Compile deterministic resolution plans from multi-tool commerce evidence.
- Simulate fee/shipping/outcome before executing user actions.
- Enforce preflight safety checks, idempotent execution, and resumable plan state.
