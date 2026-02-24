# I-0354 — Chat Multi-LLM Routing (Failover + Cost Steering, 개정 v2)

## Priority
- P1

## Dependencies
- I-0350, I-0352, I-0353
- I-0365

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

### 5) Quality-aware routing layer (신규)
- groundedness/actionability/해결률 지표를 라우팅 가중치에 반영
- 비용 최적화가 품질 컷라인을 침범하면 자동으로 고신뢰 경로 승격
- 특정 인텐트 버킷만 provider override 가능한 부분 정책 지원

## Runbook integration
- provider 장애별 대응 절차를 `docs/RUNBOOK.md`와 연결
- 자동 failover 실패 시 온콜 escalation 룰 명시

## Observability
- `chat_provider_route_total{provider,result}`
- `chat_provider_failover_total{from,to,reason}`
- `chat_provider_cost_per_1k{provider}`
- `chat_provider_health_score{provider}`
- `chat_provider_forced_route_total{provider,reason}`
- `chat_provider_quality_weight{provider,intent}`

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
- 비용-품질 동시 제약 라우팅(quality-aware)이 운영 지표로 검증됨

## Codex Prompt
Implement multi-provider LLM routing for chat:
- Compute provider health and route by policy tiers.
- Fail over automatically on outages, timeouts, and quota breaches.
- Add cost-aware steering, operator overrides, and full decision telemetry.

## Implementation Update (2026-02-23, Bundle 12)
- [x] 다중 LLM provider failover 체인 도입
  - `QS_LLM_URL` + `QS_LLM_FALLBACK_URLS`(comma-separated) 기반 provider 체인 구성
  - provider alias: `primary`, `fallback_1..N`
- [x] JSON 생성 경로 failover 적용
  - `/v1/generate` 호출에서 `429`, `5xx`, timeout/network 오류 발생 시 다음 provider로 전환
  - 비-failover 대상(일반 4xx)은 즉시 실패 처리
- [x] SSE 스트리밍 경로 failover 적용
  - 스트리밍 시작 전 `429`, `5xx`, timeout/network 오류 시 다음 provider로 전환
  - 토큰 송신 시작 후에는 provider 전환 없이 현재 경로 실패 처리
- [x] 라우팅/전환 메트릭 추가
  - `chat_provider_route_total{provider,result,mode}`
  - `chat_provider_failover_total{from,to,reason,mode}`
- [x] 회귀 테스트 추가
  - primary 500 응답 시 fallback provider 성공 경로 및 메트릭 증가 검증

## Implementation Update (2026-02-23, Bundle 13)
- [x] 운영자 강제 라우팅(override) 추가
  - `QS_LLM_FORCE_PROVIDER` 환경변수로 provider alias(`primary`, `fallback_n`) 또는 URL 지정 가능
  - 강제 provider가 유효하면 해당 provider를 체인 선두로 재정렬
- [x] 강제 라우팅 관측 지표 추가
  - `chat_provider_forced_route_total{provider,reason,mode}`
  - reason: `selected`(적용), `not_found`(미존재 provider 지정)
- [x] 회귀 테스트 추가
  - 강제 provider 지정 시 실제 호출 URL이 fallback provider로 선행되는지 검증

## Implementation Update (2026-02-23, Bundle 14)
- [x] 비용 스티어링(초기형) 추가
  - `QS_LLM_COST_STEERING_ENABLED=1`일 때 `QS_LLM_LOW_COST_PROVIDER`를 체인 선두로 재정렬
  - 단, 주문/결제/환불/배송 등 고위험 질의는 비용 스티어링을 우회하고 기본 체인을 유지
- [x] 비용 스티어링 메트릭 추가
  - `chat_provider_cost_steer_total{provider,reason,mode}`
  - reason: `selected`, `high_risk_bypass`, `not_configured`, `not_found`
- [x] 회귀 테스트 추가
  - 저위험 질의에서 저비용 provider 우선 호출 및 메트릭 증가 검증

## Implementation Update (2026-02-23, Bundle 15)
- [x] provider 쿨다운 기반 health 라우팅 추가
  - `QS_LLM_PROVIDER_COOLDOWN_SEC` 동안 timeout/429/5xx 발생 provider를 임시 비선호 처리
  - 가용 provider가 있으면 쿨다운 provider를 뒤로 보내 flapping 완화
  - 전 provider가 쿨다운 상태면 기본 체인을 유지해 전면 차단은 방지
- [x] health 상태 갱신
  - 실패 시 provider 쿨다운 마킹
  - 성공 시 provider 쿨다운 즉시 해제
- [x] 회귀 테스트 추가
  - primary provider 쿨다운 상태에서 fallback provider가 선행 호출되는지 검증
  - `chat_provider_route_total{result=cooldown_skip}` 메트릭 검증

## Implementation Update (2026-02-23, Bundle 16)
- [x] provider health score 집계 추가
  - provider별 성공/실패 카운트를 캐시에 누적하고 health score를 계산
  - `chat_provider_health_score{provider}` gauge 갱신
- [x] provider 비용 계측 추가
  - `QS_LLM_PROVIDER_COSTS_JSON`(alias/url → cost per 1k) 설정 파싱
  - provider 성공/실패 처리 시 `chat_provider_cost_per_1k{provider}` gauge 갱신
- [x] stream/json 공통 반영
  - JSON/스트리밍 모두 provider 결과에 health/cost telemetry를 기록
- [x] 회귀 테스트 추가
  - failover 시 provider health score 갱신 검증
  - 저비용 라우팅 시 provider cost metric 노출 검증

## Implementation Update (2026-02-23, Bundle 17)
- [x] 스트리밍 경로 failover 회귀 테스트 추가
  - 첫 provider가 `503`을 반환하면 첫 토큰 이전에 fallback provider로 자동 전환되는지 검증
  - 스트리밍 응답(`delta`, `done.citations`)이 fallback provider 기준으로 정상 수집되는지 확인
- [x] stream failover 메트릭 검증
  - `chat_provider_failover_total{mode=stream}` 증가 확인
  - fallback provider `chat_provider_route_total{result=ok}` 증가 확인

## Implementation Update (2026-02-23, Bundle 18)
- [x] Runbook 연동
  - `docs/RUNBOOK.md`에 책봇 다중 provider 운영 섹션 추가
  - failover/강제 라우팅/비용 스티어링 환경변수와 점검 절차를 명시
  - 운영 중 확인해야 하는 핵심 메트릭 목록 정리

## Implementation Update (2026-02-23, Bundle 19)
- [x] 비용 스티어링 안전장치 회귀 테스트 추가
  - 고위험 질의(환불/배송 등)에서 비용 스티어링이 bypass 되고 primary provider가 유지되는지 검증
  - `chat_provider_cost_steer_total{reason=high_risk_bypass}` 메트릭 검증

## Implementation Update (2026-02-23, Bundle 20)
- [x] 운영자 수동 차단(blocklist) 추가
  - `QS_LLM_PROVIDER_BLOCKLIST`(alias/url comma-separated)로 provider 라우팅 제외
  - 잘못된 blocklist로 전부 차단된 경우에는 가용성 보존을 위해 기본 체인으로 자동 복귀
- [x] health score 기반 우선순위 라우팅 추가
  - `QS_LLM_HEALTH_ROUTING_ENABLED`, `QS_LLM_HEALTH_MIN_SAMPLE` 기반 provider 정렬
  - provider 통계가 충분하면 높은 성공률 provider를 우선 호출
- [x] 회귀 테스트 추가
  - blocklist 적용 시 fallback provider 우선 호출 검증
  - health score 우위 provider 선호 호출 검증

## Implementation Update (2026-02-23, Bundle 21)
- [x] 강제 라우팅 vs blocklist 충돌 처리 보강
  - 강제 provider가 blocklist로 제외된 경우 override를 건너뛰고 안전 경로로 라우팅
  - `chat_provider_forced_route_total{reason=blocked}`로 운영자 가시성 확보
- [x] 회귀 테스트 추가
  - `QS_LLM_FORCE_PROVIDER`와 `QS_LLM_PROVIDER_BLOCKLIST` 충돌 시 fallback provider로 정상 우회되는지 검증

## Implementation Update (2026-02-23, Bundle 22)
- [x] 인텐트별 provider 부분 정책 추가
  - `QS_LLM_PROVIDER_BY_INTENT_JSON`으로 `REFUND/SHIPPING/ORDER/GENERAL`별 provider 지정
  - 지정된 인텐트 정책이 유효하면 해당 provider를 우선 라우팅
- [x] 인텐트 라우팅 메트릭 추가
  - `chat_provider_intent_route_total{intent,provider,reason,mode}`
  - reason: `selected`, `no_policy`, `not_found`
- [x] 회귀 테스트 추가
  - 배송 질의(`SHIPPING`)에서 지정 provider가 우선 호출되는지 검증

## Implementation Update (2026-02-23, Bundle 23)
- [x] health score에 최근 연속 실패 페널티 반영
  - provider 통계에 `streak_fail`를 저장하고 effective health score 계산
  - `QS_LLM_HEALTH_STREAK_PENALTY_STEP`, `QS_LLM_HEALTH_STREAK_PENALTY_MAX`로 페널티 튜닝
- [x] 관측 강화
  - `chat_provider_health_penalty{provider}` gauge 추가
  - 기존 `chat_provider_health_score{provider}`는 effective score를 노출
- [x] 회귀 테스트 추가
  - base ratio가 높은 provider라도 연속 실패가 크면 우선순위가 내려가는지 검증

## Implementation Update (2026-02-23, Bundle 24)
- [x] stream 인텐트 라우팅 회귀 테스트 추가
  - 스트리밍 질의(`SHIPPING`)에서도 인텐트 정책 provider가 선행 적용되는지 검증
- [x] blocklist 안전장치 회귀 테스트 추가
  - provider 전부 차단 오설정 시에도 기본 체인으로 복귀하여 가용성이 유지되는지 검증

## Implementation Update (2026-02-23, Bundle 25)
- [x] 운영 진단용 라우팅 디버그 추가
  - `/internal/rag/explain` 응답에 `llm_routing` 블록 포함
  - blocklist/forced/intent/cost/health/final_chain/provider_stats를 한 번에 확인 가능
- [x] 회귀 테스트 추가
  - explain 응답에 라우팅 디버그 필드 존재 검증
  - 강제 라우팅과 blocklist 충돌 시 explain에서 `forced_blocked=true` 확인

## Implementation Update (2026-02-23, Bundle 26)
- [x] `/internal/rag/explain` 입력 안정성 보강
  - invalid JSON body 요청 시 500 대신 표준 `invalid_request` 400으로 응답
- [x] 회귀 테스트 추가
  - explain endpoint invalid JSON 요청 시 에러 코드/상태값 검증

## Implementation Update (2026-02-23, Bundle 27)
- [x] chat provider 운영 스냅샷 endpoint 추가
  - `GET /internal/chat/providers`에서 현재 라우팅 정책/최종 체인/provider 통계를 제공
  - explain endpoint의 `llm_routing` 디버그 블록과 같은 판단 기준 공유
- [x] SSOT 반영
  - `docs/API_SURFACE.md`에 endpoint 추가
  - `contracts/chat-provider-snapshot-response.schema.json` 및 sample 추가
- [x] 회귀 테스트 추가
  - `/internal/chat/providers` 응답 shape 검증

## Implementation Update (2026-02-23, Bundle 28)
- [x] session 단위 챗봇 진단 endpoint 추가
  - `GET /internal/chat/session/state?session_id=...`
  - fallback 누적 횟수, 티켓 전환 임계치, 미해결 컨텍스트(reason/trace/request/query preview) 노출
- [x] SSOT 반영
  - `contracts/chat-session-state-response.schema.json` + sample 추가
  - `docs/API_SURFACE.md`, `docs/RUNBOOK.md` 반영
- [x] 회귀 테스트 추가
  - session state core 함수 fallback/unresolved snapshot 검증
  - endpoint 정상/필수 파라미터 누락 에러 검증

## Implementation Update (2026-02-23, Bundle 29)
- [x] LLM Gateway toy 응답 한국어화
  - 근거 부족 메시지를 한국어로 고정해 UI 영어 문구 노출 제거
  - toy 요약 응답 문구도 한국어로 통일
- [x] 회귀 테스트 반영
  - no-context insufficiency 응답 문구 한국어 검증

## Implementation Update (2026-02-23, Bundle 30)
- [x] output guard 차단 메시지 한국어 통일
  - 스트리밍/JSON 경로 공통으로 `output guard blocked` 영문 문구 제거
  - 사용자 노출 메시지를 `응답 품질 검증에서 차단되었습니다.`로 표준화
- [x] 회귀 테스트 추가
  - stream guard 차단 시 에러 이벤트 메시지 한국어 노출 검증

## Implementation Update (2026-02-23, Bundle 31)
- [x] session 진단 응답 실행가능 정보 확장
  - unresolved context에 `reason_message`, `next_action` 추가
  - 운영자가 reason code 해석 없이 즉시 재시도/티켓 전환 분기 가능
- [x] SSOT/테스트 반영
  - `chat-session-state-response` contract + sample 확장
  - core/route 테스트에서 신규 필드 검증
