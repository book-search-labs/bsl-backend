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

## Implementation Update (2026-02-23, Bundle 32)
- [x] session 진단 endpoint 운영 메트릭 추가
  - `chat_session_state_requests_total{result,has_unresolved}` 집계
  - `result`: `ok`, `missing_session_id`, `invalid_session_id`
- [x] 회귀 테스트 추가
  - 정상/필수 파라미터 누락/형식 오류 케이스에서 메트릭 라벨 검증

## Implementation Update (2026-02-23, Bundle 33)
- [x] session 진단 reset endpoint 추가
  - `POST /internal/chat/session/reset`로 fallback 카운터/미해결 컨텍스트 초기화
  - 응답에 reset 전 상태(`previous_fallback_count`, `previous_unresolved_context`) 포함
- [x] SSOT 반영
  - `chat-session-reset-response` contract + sample 추가
  - API surface / runbook 문서 반영
- [x] 운영 메트릭/회귀 테스트 추가
  - `chat_session_reset_requests_total{result,had_unresolved}` 집계
  - 정상/필수값 누락/세션 형식 오류/JSON 파싱 오류 케이스 검증

## Implementation Update (2026-02-23, Bundle 34)
- [x] session state 응답에 최종 권장 액션 추가
  - `recommended_action`, `recommended_message` 필드 제공
  - fallback 임계치 초과 시 `OPEN_SUPPORT_TICKET`를 우선 권장
- [x] SSOT/테스트 반영
  - `chat-session-state-response` contract + sample 확장
  - state core/route 테스트에서 권장 액션 필드 검증

## Implementation Update (2026-02-23, Bundle 35)
- [x] ticket 접수 성공 후 세션 컨텍스트 자동 정리
  - support ticket 생성/중복 재사용 성공 시 unresolved context/fallback counter 자동 초기화
  - 반복 실패 후 티켓 접수 시 stale fallback 상태가 남지 않도록 보정
- [x] 운영 메트릭/회귀 테스트 추가
  - `chat_ticket_context_reset_total{reason=ticket_created|ticket_reused}` 집계
  - unresolved context 기반 ticket 생성/중복 재사용 케이스에서 캐시 정리 검증

## Implementation Update (2026-02-23, Bundle 36)
- [x] BFF 챗 세션 진단 프록시 endpoint 추가
  - `GET /chat/session/state` (`/v1/chat/session/state`)
  - `POST /chat/session/reset` (`/v1/chat/session/reset`)
  - 프론트가 Query Service 내부 경로를 직접 호출하지 않도록 표준 진입점 제공
- [x] BFF 회귀 테스트 추가
  - ChatController에서 state/reset 프록시 정상/필수값 누락 검증
- [x] 문서 반영
  - API surface 및 runbook에 BFF 경유 호출 예시 추가

## Implementation Update (2026-02-23, Bundle 37)
- [x] BFF alias 회귀 테스트 보강
  - `/v1/chat/session/state`, `/v1/chat/session/reset` alias 동작 검증
  - 프론트 라우팅 기준 endpoint prefix 변화 시 회귀 방지

## Implementation Update (2026-02-24, Bundle 38)
- [x] support ticket 생성 쿨다운 도입
  - 동일 세션에서 연속 ticket 생성 시도 시 `QS_CHAT_TICKET_CREATE_COOLDOWN_SEC`(기본 30초) 쿨다운 적용
  - 쿨다운 중 응답은 `reason_code=RATE_LIMITED`, `next_action=RETRY`, `retry_after_ms`로 표준 복구 힌트 반환
- [x] 중복/성공 경로 정합성 유지
  - dedup 재사용 경로와 실제 ticket 생성 성공 경로 모두 마지막 생성 시각 캐시를 갱신
- [x] 회귀 테스트 추가
  - 동일 세션 내 비중복 ticket 연속 생성 시 두 번째 요청이 rate limit 차단되는지 검증

## Implementation Update (2026-02-24, Bundle 39)
- [x] ticket 생성 쿨다운 관측 라벨 확장
  - `chat_ticket_create_rate_limited_total`에 `result=pass`, `result=dedup_bypass` 라벨 집계 추가
  - 차단(`blocked`) 뿐 아니라 정상 통과/중복 재사용 bypass 비율까지 운영 대시보드에서 분리 관측 가능
- [x] 회귀 테스트 보강
  - 쿨다운 차단 케이스에서 `chat_ticket_create_rate_limited_total{result=blocked}` 증가 검증

## Implementation Update (2026-02-24, Bundle 40)
- [x] ticket 생성 쿨다운을 사용자 범위로 확장
  - 기존 `session_id` 캐시 외에 `user_id` 캐시를 함께 저장/조회하여 교차 세션 반복 접수도 제한
  - 동일 사용자 다중 탭/다중 세션에서 단시간 spam ticket 생성 방지
- [x] 회귀 테스트 추가
  - 같은 `user_id`, 다른 `session_id`에서 연속 ticket 생성 시 두 번째 요청이 `RATE_LIMITED`로 차단되는지 검증

## Implementation Update (2026-02-24, Bundle 41)
- [x] 최근 문의번호 캐시를 사용자 범위로 확장
  - 마지막 접수번호를 `session_id` + `user_id` 양쪽에 저장해 세션 이동 시에도 상태조회 연속성 유지
- [x] 쿨다운 차단 응답 안내 강화
  - 쿨다운(`RATE_LIMITED`) 응답에 최근 접수번호를 함께 제공해 즉시 문의 상태 조회 유도
- [x] 회귀 테스트 추가
  - 다른 세션에서도 사용자 최근 접수번호를 기반으로 `내 문의 상태` 조회가 동작하는지 검증

## Implementation Update (2026-02-24, Bundle 42)
- [x] 쿨다운 차단 응답 근거(citation) 추가
  - `RATE_LIMITED` 응답에도 `ticket_create_cooldown` source/citation을 포함해 UI 근거 배지 유지
  - 사용자 안내 메시지와 함께 운영 근거(`remaining_sec`, `recent_ticket_no`)를 source snippet으로 제공
- [x] 회귀 테스트 보강
  - 쿨다운 차단 응답에서 citation/source endpoint가 채워지는지 검증

## Implementation Update (2026-02-24, Bundle 43)
- [x] ticket 생성 dedup을 사용자 범위로 확장
  - 기존 세션 dedup 키와 함께 사용자 dedup 키를 저장/조회해 교차 세션 동일 문의도 티켓 재사용
  - 사용자 dedup hit 시 신규 티켓 생성/쿨다운 차단 대신 기존 접수번호를 즉시 반환
- [x] 운영 관측 지표 추가
  - `chat_ticket_create_dedup_scope_total{scope=session|user}`로 dedup 재사용 범위를 분리 집계
- [x] 회귀 테스트 추가
  - 같은 `user_id`, 다른 `session_id`에서 동일 문의 접수 시 두 번째 요청이 재사용되는지 검증

## Implementation Update (2026-02-24, Bundle 44)
- [x] dedup 캐시 최신성 우선 선택 로직 추가
  - 세션/user dedup 엔트리가 동시에 존재할 때 `cached_at` 기준 최신 엔트리를 우선 선택
  - 세션 이동/재진입 시 과거 stale dedup 응답을 반환하지 않도록 보정
- [x] 회귀 테스트 추가
  - session/user dedup 캐시에 서로 다른 ticket_no가 있을 때 최신 엔트리가 선택되는지 검증

## Implementation Update (2026-02-24, Bundle 45)
- [x] 최근 문의번호 캐시 TTL 환경변수화
  - `QS_CHAT_LAST_TICKET_TTL_SEC`(기본 86400초, 최소 600초) 추가
  - 세션/사용자 범위 최근 문의번호 캐시에 동일 TTL 적용
- [x] 회귀 테스트 추가
  - TTL 설정값이 실제 캐시 만료시각에 반영되는지 검증

## Implementation Update (2026-02-24, Bundle 46)
- [x] session reset에 티켓 세션 컨텍스트 초기화 연동
  - `reset_chat_session_state`에서 ticket session context reset을 함께 호출
  - fallback/unresolved뿐 아니라 세션 범위 최근 문의번호/쿨다운 timestamp/dedup epoch를 동기화 초기화
- [x] dedup epoch 분리 도입
  - 세션 dedup key에 epoch를 포함해 reset 이후 stale dedup 키를 무효화
- [x] 회귀 테스트 추가
  - session reset 시 ticket session context reset 함수 호출 검증
  - ticket session context reset 시 epoch 증가 및 session dedup 비활성화 검증

## Implementation Update (2026-02-24, Bundle 47)
- [x] session reset 사용자 범위 캐시 초기화 연동
  - `session_id`가 `u:<user_id>:` 패턴이면 사용자 범위 최근 문의번호/쿨다운 캐시도 함께 clear 처리
- [x] 운영 관측 지표 반영
  - `chat_ticket_context_reset_total{reason=session_reset}`를 session reset 경로에서 집계
- [x] 회귀 테스트 추가
  - session pattern 기반 사용자 캐시 clear 및 `session_reset` 메트릭 증가 검증

## Implementation Update (2026-02-24, Bundle 48)
- [x] session reset 범위 메트릭 추가
  - `chat_ticket_context_reset_scope_total{scope=session_only|session_and_user}` 집계
  - 사용자 패턴 세션과 일반 세션의 reset 범위를 운영 대시보드에서 분리 확인 가능
- [x] 회귀 테스트 추가
  - `u:<user_id>:` 세션에서 `scope=session_and_user` 증가 검증
  - 일반 세션에서 `scope=session_only` 증가 검증

## Implementation Update (2026-02-24, Bundle 49)
- [x] 사용자 dedup epoch 추가
  - 사용자 dedup cache key에 epoch를 포함해 reset 이후 stale 사용자 dedup 엔트리 무효화
  - `u:<user_id>:` 패턴 세션 reset 시 사용자 dedup epoch도 함께 증가
- [x] 회귀 테스트 보강
  - 사용자 패턴 세션 reset 시 사용자 dedup epoch 증가 및 user dedup 조회 무효화 검증

## Implementation Update (2026-02-24, Bundle 50)
- [x] session pattern 파싱 확장
  - 사용자 세션 파싱을 `u:<user_id>:` 뿐 아니라 `u:<user_id>` 형식까지 지원
- [x] session reset 범위 안전성 테스트 보강
  - `u:<user_id>` 세션에서 사용자 캐시 clear 동작 검증
  - 일반 세션 reset 시 사용자 캐시가 유지되는지 검증

## Implementation Update (2026-02-24, Bundle 51)
- [x] 세션 캐시 소유자 검증 추가
  - 최근 문의번호/티켓 생성 쿨다운 세션 캐시에 `user_id`를 저장하고 조회 시 소유자 일치 여부 검증
  - 소유자가 다르면 세션 캐시는 무시하고 사용자 캐시만 사용
- [x] 회귀 테스트 추가
  - 소유자 불일치 세션 캐시가 조회에서 제외되는지 검증
  - 소유자 불일치 세션 쿨다운이 신규 사용자 ticket 생성을 차단하지 않는지 검증

## Implementation Update (2026-02-24, Bundle 52)
- [x] 세션 캐시 소유자 mismatch 관측 메트릭 추가
  - `chat_ticket_session_cache_owner_mismatch_total{cache=last_ticket|create_last}` 집계
  - 비정상 세션 공유/클라이언트 버그로 인한 소유자 불일치 신호를 운영에서 즉시 감지 가능
- [x] 회귀 테스트 보강
  - `last_ticket`/`create_last` owner mismatch 시 메트릭 증가 검증

## Implementation Update (2026-02-24, Bundle 53)
- [x] 쿨다운 차단 컨텍스트 메트릭 추가
  - `chat_ticket_create_rate_limited_context_total{has_recent_ticket=true|false}` 집계
  - 차단 응답에서 최근 접수번호 안내 포함 비율을 운영 관점에서 분리 관측 가능
- [x] 회귀 테스트 보강
  - 최근 접수번호가 있는 차단 케이스(`has_recent_ticket=true`) 메트릭 검증
  - 최근 접수번호가 없는 차단 케이스(`has_recent_ticket=false`) 메트릭 검증

## Implementation Update (2026-02-24, Bundle 54)
- [x] dedup 조회 단계 관측 메트릭 추가
  - `chat_ticket_create_dedup_lookup_total{result=miss|session|user}`로 조회 경로를 분리 집계
  - 신규 접수 전환(miss)과 세션/사용자 재사용 경로를 운영 대시보드에서 즉시 구분 가능
- [x] dedup 동시 후보 타이브레이크 보정
  - session/user dedup의 `cached_at`이 동일할 때 세션 후보를 우선 선택하도록 결정 규칙 고정
  - 동일 timestamp에서 비결정적 재사용 결과가 바뀌지 않도록 안정화
- [x] 회귀 테스트 보강
  - dedup 조회 miss/session/user 메트릭 증가 검증
  - `cached_at` 동률일 때 session dedup 선택 검증

## Implementation Update (2026-02-24, Bundle 55)
- [x] 티켓 상태 조회 접수번호 자동 보정 추가
  - `내 문의 상태` 질의에서 접수번호/캐시가 없으면 `GET /api/v1/support/tickets?limit=1`로 최신 문의를 조회해 자동 보정
  - 최신 문의를 찾으면 세션/사용자 최근 접수번호 캐시에 다시 저장해 이후 상태 조회 연속성 확보
- [x] 티켓 상태 조회 소스 관측 지표 추가
  - `chat_ticket_status_lookup_ticket_source_total{source=query|cache|list|missing}` 집계
  - 질의 파싱/캐시/목록 보정/미해결 경로를 운영 관점에서 분리 추적 가능
- [x] 회귀 테스트 보강
  - 접수번호 없이도 최근 문의 목록 기반으로 상태 조회 성공하는지 검증
  - 최근 문의가 없는 경우 `needs_input`으로 접수번호 입력 안내 및 메트릭 증가 검증

## Implementation Update (2026-02-24, Bundle 56)
- [x] 최근 문의 자동 조회 실패/빈목록 구분 처리
  - 최근 문의 조회 실패(`error`)와 빈 목록(`empty`)을 분리해 `needs_input` 안내 메시지/집계 라벨을 명확화
  - 최근 문의 조회 결과를 `chat_ticket_status_recent_lookup_total{result=found|empty|error}`로 관측
- [x] stale 캐시 접수번호 자동 복구 추가
  - 캐시 접수번호 조회가 `not_found`면 최신 문의 목록으로 1회 재조회 후 새로운 접수번호로 재시도
  - 복구 성공/실패를 `chat_ticket_status_lookup_cache_recovery_total{result=recovered|miss|retry_failed}`로 분리 집계
- [x] 회귀 테스트 보강
  - 최근 문의 조회 timeout/error 시 `recent_lookup_error` 처리 검증
  - stale cache(`not_found`)에서 최신 접수번호 재시도 후 복구 성공 경로 검증

## Implementation Update (2026-02-24, Bundle 57)
- [x] 티켓 상태 응답 정보 밀도 강화
  - 상태 조회 응답에 문의 유형(category), 중요도(severity), 예상 첫 응답 시간(분) 정보를 포함해 사용자 안내를 구체화
  - 분류값이 비어도 안전한 한국어 기본값(`미분류`, `미지정`)을 사용해 문구 품질 유지
- [x] 회귀 테스트 보강
  - 상태 조회 응답에 유형/중요도/예상 응답시간이 포함되는지 검증

## Implementation Update (2026-02-24, Bundle 58)
- [x] 접수번호 기반 티켓 상태 의도 판별 보강
  - 사용자 메시지에 `STK...` 접수번호가 포함되면 별도 상태 키워드가 없어도 `TICKET_STATUS`로 라우팅
  - 단순 접수번호/확인형 문장에서도 즉시 상태 조회 동작
- [x] 회귀 테스트 보강
  - `STK... 확인해줘` 패턴에서 티켓 상태 조회 경로가 정상 실행되는지 검증
  - source metric(`source=query`) 집계 증가 검증
