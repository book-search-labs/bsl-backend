# B-0305 — 이벤트 멱등키(dedup_key) 표준화 가이드(전 event_type 공통)

## Goal
Outbox→Kafka 파이프라인에서 모든 이벤트가
- 재시도/중복 전송에도 안전하고
- 컨슈머가 멱등 처리 가능하도록
  **dedup_key(멱등키) 규칙을 표준화**한다.

## Why
- 클릭/노출/선택/드웰/구매 이벤트는 재전송이 흔함(네트워크, 장애, 재처리)
- 멱등키가 없으면 CTR/Popularity 집계가 뻥튀기되어 랭킹이 망가짐

## Scope
### 1) 공통 이벤트 envelope 규격
- `event_type`
- `event_time` (UTC)
- `request_id`, `trace_id`, `session_id`
- `producer`(service, version)
- `payload`(event specific)
- `dedup_key` (필수)

### 2) dedup_key 생성 규칙(권장)
dedup_key는 **“같은 현실 세계 사건”** 을 대표해야 함.

- **search_impression**
  - key = `imp:{imp_id}` (imp_id는 server-generated UUID)
- **click**
  - key = `clk:{imp_id}:{doc_id}:{position}` (+ timestamp bucket optional)
- **dwell**
  - key = `dwl:{imp_id}:{doc_id}` (dwell은 누적 업데이트는 별도 정책)
- **ac_impression**
  - key = `acimp:{ac_req_id}`
- **ac_select**
  - key = `acsel:{ac_req_id}:{selected_text}`

> 중요한 원칙:
- “client timestamp”가 아니라 **server-issued id**(imp_id/ac_req_id)를 포함
- position/문서 id 같은 구분자를 넣어 이벤트 단위를 고정

### 3) outbox_event 테이블 연동
- BFF/서비스가 outbox_event에 저장 시:
  - `dedup_key` NOT NULL + UNIQUE 강제(이미 스키마 있음)
- 컨슈머는 dedup_key 기준으로 “처리 이력 테이블” 또는 KV로 중복 제거

### 4) Consumer idempotency 전략
- v1: `consumer_dedup` 테이블(혹은 Redis set)로 최근 N일 dedup_key 저장
- v2: exactly-once에 가까운 설계(트랜잭션 + offsets)까지 확장 가능

## Non-goals
- 완전한 EOS(Exactly Once Semantics) 보장
- Schema Registry 도입 자체(I 티켓)

## DoD
- 모든 event_type에 대한 dedup_key 규칙 문서가 존재
- Producer가 동일 규칙으로 dedup_key를 생성해 outbox에 기록
- Aggregator/Consumer가 dedup 처리로 중복 집계가 발생하지 않음
- 재처리(replay) 시에도 결과가 안정적(중복 증가 없음)

## Codex Prompt
Standardize dedup_key for all events:
- Define a common event envelope including dedup_key and required tracing fields.
- Specify dedup_key formulas per event_type using server-issued ids (imp_id/ac_req_id).
- Ensure producers write outbox_event with UNIQUE(dedup_key) and consumers implement idempotent processing using a dedup store.
- Add documentation and minimal tests showing replay does not inflate aggregates.
