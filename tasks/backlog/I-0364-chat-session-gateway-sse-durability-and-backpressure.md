# I-0364 — Chat Session Gateway (SSE Durability + Backpressure)

## Priority
- P0

## Dependencies
- I-0353, I-0355
- I-0363, U-0154

## Goal
우측 고정형 실시간 위젯 트래픽을 안정적으로 수용하기 위해 세션 게이트웨이의 연결 지속성/복구/과부하 제어를 표준화한다.

## Scope
### 1) Session gateway durability
- SSE(또는 WebSocket) 연결 상태 추적 및 heartbeat 표준화
- 서버 재시작/네트워크 단절 시 세션 resume token 기반 복구
- 다중 인스턴스 환경에서 세션 affinity + failover 전략 적용

### 2) Event delivery guarantees
- turn/event 순서 보장(ordered delivery)과 중복 이벤트 제거
- 클라이언트 ACK 기반 재전송 정책(최대 재시도/TTL) 정의
- reconnect 시 누락 메시지 재동기화 범위 표준화

### 3) Backpressure and admission control
- queue depth/latency 기반 동적 rate shaping
- 고부하 시 저우선 트래픽 제한 + 핵심 인텐트 보호
- circuit open 시 사용자에게 명시적 대기/재시도 가이드 노출

### 4) Resilience drills
- connection storm, partial region fail, broker delay 시나리오 주기적 게임데이
- 복구 시간(RTO)과 메시지 손실률(SLO) 측정

## Observability
- `chat_session_connection_active`
- `chat_session_reconnect_total{reason}`
- `chat_event_redelivery_total`
- `chat_backpressure_drop_total{priority}`
- `chat_session_resume_success_rate`

## DoD
- 연결 단절 후 세션 복구 성공률이 운영 목표를 만족
- 피크 트래픽에서도 핵심 인텐트 지연/실패율이 관리 기준 내 유지
- 게임데이 리포트에 복구 시간/손실률/개선 과제가 자동 기록됨

## Codex Prompt
Harden chat realtime session infrastructure:
- Build durable SSE/WebSocket session gateway with resume tokens.
- Guarantee ordered event delivery with bounded redelivery.
- Apply adaptive backpressure/admission control under load.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Session gateway durability gate 추가
  - `scripts/eval/chat_session_gateway_durability.py`
  - 세션 이벤트(`connect/disconnect/heartbeat/reconnect/resume/failover`)를 집계해 reconnect/resume 성공률, heartbeat miss ratio, affinity miss ratio를 계산
  - gate 모드에서 resume/reconnect 성공률 하락, heartbeat miss 증가, affinity miss 증가, stale window 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_session_gateway_durability.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SESSION_DURABILITY_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Event delivery guarantee gate 추가
  - `scripts/eval/chat_event_delivery_guarantee.py`
  - 전달 이벤트(`event_seq/expected_seq/duplicate/acked/redelivery_count/sync_gap_events`)를 집계해 ordered delivery 위반, 중복, ACK 누락, TTL 드롭을 검증
  - gate 모드에서 delivery success ratio 하락, ordered violation 증가, duplicate/ack missing 비율 증가, sync gap/TTL 드롭 임계치 초과 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_event_delivery_guarantee.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_EVENT_DELIVERY_GUARANTEE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Backpressure admission guard 추가
  - `scripts/eval/chat_backpressure_admission_guard.py`
  - backpressure 이벤트(`priority/admitted/dropped/queue_depth/queue_latency_ms/circuit_open/user_guidance_sent`)를 집계해 drop ratio, core intent 보호율, queue p95, 안내 누락을 검증
  - gate 모드에서 critical drop 발생, core intent 보호율 저하, queue p95 초과, circuit-open 안내 누락 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_backpressure_admission_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_BACKPRESSURE_ADMISSION_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Session resilience drill report gate 추가
  - `scripts/eval/chat_session_resilience_drill_report.py`
  - drill 이벤트(`scenario/completed/passed/rto_sec/message_loss_total/sent_total`)를 집계해 scenario별 성공률, open drill, RTO, 메시지 손실률을 계산
  - 필수 시나리오(`CONNECTION_STORM/PARTIAL_REGION_FAIL/BROKER_DELAY`) 커버리지 누락을 감지
  - gate 모드에서 open drill, 평균 RTO, 손실률, 시나리오 누락, stale evidence 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_session_resilience_drill_report.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_SESSION_RESILIENCE_DRILL_REPORT=1 ./scripts/test.sh`
