# I-0354 — Chat Multi-LLM Routing (Failover + Cost Steering)

## Priority
- P1

## Dependencies
- I-0350, I-0352, I-0353

## Goal
LLM 제공자 장애/지연/비용 급등 상황에서 자동 라우팅/페일오버로 챗봇 가용성과 비용 안정성을 동시에 확보한다.

## Non-goals
- 모든 모델을 동일 품질로 맞추는 모델 튜닝은 범위 외
- 벤더별 계약/과금체계 재협상은 본 티켓 범위가 아님

## Scope
### 1) Provider health model
- provider별 성공률/지연/에러/쿼터 상태 실시간 수집
- health score 기반 우선순위 계산

### 2) Routing policy
- intent/tenant/quality tier별 provider 라우팅 전략
- 비용 상한 초과 시 저비용 경로로 자동 전환

### 3) Failover orchestration
- timeout/5xx/쿼터초과 시 fallback provider 재시도
- 무한재시도 방지 및 회로차단 연계

### 4) Evidence and control
- 라우팅 결정 이유(reason_code) 로그
- 수동 강제 라우팅/차단 스위치 제공
- provider 단위 canary 트래픽 안전 스위치 제공

## Runbook integration
- provider 장애별 대응 절차를 `docs/RUNBOOK.md`와 연결
- 자동 failover 실패 시 온콜 escalation 룰 명시

## Observability
- `chat_provider_route_total{provider,result}`
- `chat_provider_failover_total{from,to,reason}`
- `chat_provider_cost_per_1k{provider}`
- `chat_provider_health_score{provider}`
- `chat_provider_forced_route_total{provider,reason}`

## Test / Validation
- provider 다운/지연/쿼터 소진 chaos 시나리오 테스트
- 라우팅 정책 회귀 테스트(quality vs cost)
- failover 전/후 SLO 영향 비교 리포트
- provider split-brain 상황(부분 timeout)에서 flapping 방지 테스트

## DoD
- provider 장애 시 챗 응답 연속성 유지
- 비용 급등 시 자동 steering 동작 검증
- 라우팅/페일오버 의사결정 근거 추적 가능
- 수동 override 적용/복구 절차를 운영자가 5분 내 수행 가능

## Codex Prompt
Implement multi-provider LLM routing for chat:
- Compute provider health and route by policy tiers.
- Fail over automatically on outages, timeouts, and quota breaches.
- Add cost-aware steering, operator overrides, and full decision telemetry.
