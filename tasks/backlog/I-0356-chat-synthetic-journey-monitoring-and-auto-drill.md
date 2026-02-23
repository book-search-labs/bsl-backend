# I-0356 — Chat Synthetic Journey Monitoring + Auto Drill

## Priority
- P1

## Dependencies
- I-0353, I-0355, B-0378

## Goal
실사용자 장애 전에 문제를 조기 탐지하기 위해 챗 핵심 여정을 synthetic 시나리오로 상시 점검하고 자동 드릴을 수행한다.

## Non-goals
- 실사용자 트래픽을 synthetic으로 대체하지 않는다.
- 프로덕션에서 과도한 장애주입으로 사용자 영향이 발생하는 테스트는 제외한다.

## Scope
### 1) Synthetic journeys
- 검색형 질의, 주문조회, 환불문의, 티켓생성 경로를 주기 실행
- 정상/부분장애/제한모드 기대결과 정의

### 2) Auto drill
- 정해진 시간에 장애 주입(LLM 지연/tool timeout/queue 포화) 시뮬레이션
- 자동 완화/롤백 경로 동작 검증

### 3) Alerting and escalation
- 실패 시 온콜 알림 + runbook 링크
- 반복 실패는 자동 incident 생성

### 4) Evidence archive
- synthetic 실행 결과/로그/메트릭 아티팩트 저장
- 릴리즈 전후 비교 리포트 자동 생성

## Runbook integration
- drill 실패 유형별 대응 절차를 `docs/RUNBOOK.md`에 연결
- 반복 실패 자동 incident의 severity 매핑 기준 문서화

## Observability
- `chat_synthetic_run_total{journey,result}`
- `chat_synthetic_slo_violation_total{journey}`
- `chat_auto_drill_trigger_total{scenario}`
- `chat_synthetic_incident_created_total`
- `chat_synthetic_false_alarm_total{journey}`

## Test / Validation
- synthetic 시나리오 스크립트 정합성 테스트
- auto drill 안전가드(프로덕션 영향 최소화) 검증
- 실패/복구 경보 정확성 테스트
- synthetic 장애 재현성과 flakiness 비율 측정

## DoD
- 장애 조기 탐지율 개선
- 자동완화 경로 사전 검증 체계 확보
- synthetic 결과가 운영 의사결정에 활용 가능
- drill 실행 안정성(SLO)과 false alarm 기준 달성

## Codex Prompt
Implement synthetic monitoring for core chat journeys:
- Run scheduled end-to-end checks for search, commerce, and ticket flows.
- Trigger controlled auto-drills to validate remediation paths.
- Create incident-ready evidence and alerting with runbook linkage.
