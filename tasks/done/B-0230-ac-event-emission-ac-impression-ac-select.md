# B-0230 — Emit Autocomplete Events (ac_impression / ac_select) via Outbox → Kafka

## Goal
Autocomplete 사용 로그를 **표준 이벤트로 발행**해서
CTR/Popularity 집계(=B-0231)로 이어지는 “운영 루프”를 연다.

- event types: `ac_impression`, `ac_select`
- 권장: **BFF가 outbox_event에 기록** → relay가 Kafka 전송(B-0248)
- 이벤트는 **멱등(dedup_key)** 하게 설계

## Background
- autocomplete은 클릭/선택 데이터가 있어야 “좋아지는 시스템”이 된다.
- 직접 Kafka publish는 장애/재시도에서 데이터 유실 위험이 크므로
  outbox 패턴이 운영형 표준.

## Scope
### 1) Event schema (v1)
#### ac_impression
- 발생 시점: AC 응답을 내려주기 직전(“노출”의 분모)
- payload fields (minimum):
  - `event_type`: "ac_impression"
  - `event_time`
  - `request_id`, `trace_id`, `session_id` (가능하면)
  - `user_id` (익명 허용), `client` (web/mobile/admin)
  - `q_prefix` (원문), `q_prefix_norm` (정규화)
  - `candidates`: [{ `suggest_text`, `rank`, `source`(cache/os), `score` }]
  - `policy`: { `cache_hit`, `index_version`, `experiment` }

#### ac_select
- 발생 시점: 사용자가 특정 suggestion을 선택했을 때
- payload fields:
  - `event_type`: "ac_select"
  - `event_time`
  - `request_id`, `trace_id`, `session_id`, `user_id`
  - `q_prefix_norm`
  - `selected`: { `suggest_text`, `rank`, `source`, `score` }
  - (선택) `next_action`: "search_submit" | "navigate" 등

### 2) dedup_key 규칙(멱등)
- ac_impression:
  - `hash(event_type + request_id)` (request_id가 유일해야 함)
- ac_select:
  - `hash(event_type + request_id + selected.suggest_text)`
- outbox_event에 `dedup_key` UNIQUE로 중복 방지

### 3) Producer location (recommended)
- **BFF**가 `/autocomplete` 응답을 조립/리턴하면서 outbox_event 기록
- (대안) AC 서비스가 outbox_event 기록(권장 X: 분산/운영복잡도↑)

### 4) Storage
- `outbox_event` 테이블 사용 (이미 v1.1 스키마 존재)
  - status NEW/SENT/FAILED
  - relay는 B-0248 티켓에서 처리

## Non-goals
- 집계/feature 업데이트(=B-0231)
- schema registry 도입(=I-0330)
- 클릭/체류(검색 이벤트) (그건 B-0232)

## DoD
- `/autocomplete` 응답 시 ac_impression outbox 기록
- 프론트에서 선택 이벤트가 BFF로 전달되면 ac_select outbox 기록
- dedup_key로 중복 insert 방지 확인
- 로컬에서 outbox_event row가 쌓이는 smoke 테스트 완료

## Observability
- metrics:
  - outbox_new_total{type=ac_*}
  - outbox_insert_fail_total
- logs:
  - request_id, event_type, dedup_key, cache_hit

## Codex Prompt
Add autocomplete event emission:
- Define ac_impression/ac_select event payload v1.
- Emit events via outbox_event with deterministic dedup_key.
- Produce from BFF around /autocomplete response and select callback endpoint.
- Add smoke tests verifying outbox rows and dedup behavior.
