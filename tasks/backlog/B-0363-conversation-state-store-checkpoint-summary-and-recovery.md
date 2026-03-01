# B-0363 — Conversation State Store (checkpoint summary + recovery, 개정 v2)

## Priority
- P1

## Dependencies
- B-0355, U-0140
- I-0353 (SLO guardrails)
- I-0364 (session gateway durability)

## Goal
대화 상태를 안정적으로 저장/복원해 챗 세션 유실과 문맥 붕괴를 줄인다.

## Non-goals
- 장기 프로필 개인화 로직 자체를 설계하지 않는다.
- 세션 저장소를 분석/리포팅 목적 OLAP로 확장하지 않는다.

## Scope
### 1) State model
- turn event log + periodic summary checkpoint
- session metadata: locale, intent history, tool usage footprint
- assistant/tool turn 간 causal ordering key 보존
- session status(`ACTIVE/PAUSED/CLOSED`) 명시

### 2) Recovery
- stream 중단 시 마지막 안정 checkpoint부터 복원
- 재시도 시 duplicate assistant turn 방지
- 브라우저 새로고침/탭 전환/네트워크 단절 시 동일 session_id 복원
- partial tool execution 중断 시 안전 재개 또는 강제 취소

### 3) Storage policy
- TTL/보존 주기
- PII 최소화 저장 규칙 준수
- 고위험 필드(전화번호/주소/결제식별자) 저장 금지 또는 토큰화
- 사용자 삭제 요청 시 세션 상태/요약까지 연쇄 삭제

### 4) Consistency
- request_id 기반 상태 업데이트 idempotency
- stale write 방지(version check)
- 동시 요청 충돌 시 optimistic lock + 재시도 표준화

### 5) Performance/SLO
- p95 상태 조회/복원 지연 목표 설정
- checkpoint 생성 주기와 context window budget 연계

### 6) Session continuity contract (신규)
- resume token 기반 재연결 계약 정의(웹/모바일 공통)
- 멀티탭/멀티디바이스 동시 접속 시 active writer 1개 보장
- 요약 checkpoint 손상/누락 시 event log 재구성 경로 제공

## Data / Schema
- `chat_session_state` (new): session_id, user_id, status, locale, version, last_turn_at, expires_at
- `chat_session_turn` (new): session_id, turn_id, role, content_hash, tool_call_ref, created_at
- `chat_session_checkpoint` (new): session_id, checkpoint_no, summary_text, token_count, created_at
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Observability
- `chat_session_recovery_total{result}`
- `chat_session_duplicate_turn_block_total`
- `chat_session_checkpoint_latency_ms`
- `chat_session_stale_write_total`

## Test / Validation
- 세션 복원: 새로고침/재접속/스트리밍 중단 시나리오 테스트
- 멱등성: 동일 request_id 재전송 시 중복 turn 미생성
- 충돌: 동시 쓰기 충돌 시 데이터 손상 없이 재시도 성공
- 삭제: PII/세션 삭제 요청 후 재조회 불가 검증

## DoD
- 새로고침/일시 장애 후 세션 복원 성공률 목표 달성
- 중복 답변/문맥 손실 케이스 감소
- 상태 저장 계층 장애 시 degrade 동작(최소 응답) 확인
- 핵심 관측지표 대시보드에서 session health 추적 가능
- 재연결 토큰 기반 세션 연속성 검증 시나리오 통과

## Codex Prompt
Implement durable conversation state store:
- Persist turn logs with summary checkpoints.
- Support session recovery and idempotent retries.
- Enforce TTL and PII-minimized persistence.
- Add conflict-safe writes and recovery observability metrics.

## Implementation Update (2026-02-23, Bundle 7)
- [x] 세션 단기 상태 저장(경량) 보강
  - `chat:unresolved:{session_id}` 캐시에 직전 실패 질의/reason_code/trace를 저장
  - 성공 응답(LLM 정상/툴 정상/캐시 히트) 시 unresolved 상태 자동 정리
- [x] 회귀 테스트 추가
  - 성공 경로에서 unresolved 상태가 정리되는지 검증
  - tool-path 성공 경로에서 unresolved 상태가 정리되는지 검증
