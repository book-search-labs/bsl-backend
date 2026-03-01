# I-0355 — Chat Priority Queue + Load Shedding + Backpressure Control

## Priority
- P1

## Dependencies
- I-0353, I-0354, I-0350

## Goal
트래픽 급증 시 챗봇이 전체 장애로 무너지는 것을 막기 위해 우선순위 큐와 load shedding/backpressure 제어를 도입한다.

## Non-goals
- 기능 우선순위 정책을 영구 고정하지 않는다(운영 튜닝 대상).
- 장기 아키텍처 개편(메시지 브로커 교체)은 범위 외다.

## Scope
### 1) Priority classes
- 요청을 `CRITICAL/HIGH/NORMAL/LOW` 우선순위로 분류
- 주문/환불/배송 문의를 우선 처리
- 인증 상태/사용자 유형 기반 최소 공정성(fairness) 룰 추가

### 2) Queue + backpressure
- worker queue 길이 기반 수용률 자동 조절
- 임계 초과 시 저우선 요청 지연/거절

### 3) Load shedding policy
- 비핵심 기능(고급 재작성/확장 탐색) 단계적 비활성화
- 서비스 보호 모드 진입/복귀 조건 명시

### 4) User-facing degradation contract
- 제한모드에서 사용자 안내 메시지/재시도 정책 표준화
- 운영 대시보드에서 실시간 상태 노출

### 5) Admission control
- 전역 동시성/큐 길이 기준으로 request admit/reject 결정
- 우선순위별 최소 슬롯 보장(critical reserved capacity)

## Runbook integration
- 보호모드 진입/해제 조건을 `docs/RUNBOOK.md`에 명시
- 과부하 장기화 시 수동 확장/강제 모드 전환 절차 연결

## Observability
- `chat_queue_depth{priority}`
- `chat_load_shed_total{priority,reason}`
- `chat_backpressure_mode{state}`
- `chat_request_admit_rate{priority}`
- `chat_admission_reject_total{priority,reason}`

## Test / Validation
- burst 트래픽 부하 테스트
- 우선순위 역전/기아(starvation) 회귀 테스트
- 보호모드 진입/복귀 안정성 테스트
- reserved capacity 동작 및 공정성 검증 테스트

## DoD
- 피크 트래픽에서 핵심 인텐트 성공률 유지
- 전체 장애 대신 제한모드로 연속성 유지
- shedding/backpressure 동작이 지표와 로그로 추적 가능
- 과부하 구간에서 admission policy 변경 영향 분석 리포트 제공

## Codex Prompt
Harden chat runtime under traffic spikes:
- Introduce priority queues and adaptive backpressure control.
- Shed low-priority load while preserving critical commerce intents.
- Expose degradation states to users/operators with measurable telemetry.
