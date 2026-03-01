# I-0359 — Chat Traffic Partitioning + Fail-safe Isolation Mode

## Priority
- P1

## Dependencies
- I-0355, I-0358, I-0354

## Goal
문제 구간의 트래픽을 빠르게 격리해 전체 서비스 영향을 최소화하도록 파티셔닝/격리 모드를 도입한다.

## Scope
### 1) Traffic partition keys
- tenant, locale, feature flag, risk tier 기준으로 트래픽 분할
- 고위험/실험 트래픽 분리 처리

### 2) Isolation mode
- 문제 파티션만 격리 모드(제한기능/보수응답) 전환
- 정상 파티션은 영향 최소화

### 3) Fast fail-safe switches
- 운영자 원클릭 격리/복구 스위치
- 자동 조건 기반 격리 트리거(오류 급등/지연 급등)

### 4) Recovery criteria
- 격리 해제 조건(안정화 윈도우/지표 기준) 정의
- 해제 후 사후 검증 체크

## Observability
- `chat_partition_isolation_mode{partition,state}`
- `chat_partition_error_rate{partition}`
- `chat_partition_latency_p95_ms{partition}`
- `chat_partition_auto_isolation_trigger_total{reason}`

## Test / Validation
- 파티션별 장애 주입 테스트
- 격리/복구 절차 회귀 테스트
- 정상 파티션 영향도 검증 테스트

## DoD
- 국소 장애가 전체 서비스로 전파되는 비율 감소
- 격리/복구 절차 자동화 및 가시성 확보
- 운영자가 문제 파티션을 신속히 통제 가능

## Codex Prompt
Implement partition-aware fail-safe controls for chat:
- Split traffic by key dimensions and isolate unhealthy partitions.
- Provide automatic/manual isolation triggers with fast rollback.
- Ensure healthy partitions continue serving during localized incidents.
