# B-0248 — Outbox → Kafka Relay (Idempotent, Retry-safe)

## Goal
서비스에서 발생한 이벤트를 **DB Outbox**에 기록하고, 별도 Relay가 **Kafka로 안전 전송**하도록 만든다.

- 멱등 전송(dedup_key)
- 재시도/장애 복구
- DLQ/재처리(인프라 티켓과 연결)
- 최소한 “exactly-once에 가깝게” 동작(consumer는 idem 가정)

## Background
- 서빙 요청에서 바로 Kafka publish하면:
  - publish 실패/중복/순서 문제가 운영에서 지옥이 된다.
- Outbox 패턴은 “DB 트랜잭션 안에서 이벤트 기록”을 보장한다.

## Scope
### 1) DB (already exists)
`outbox_event` 테이블 사용:
- dedup_key NOT NULL + UNIQUE
- status: NEW/SENT/FAILED
- sent_at 기록

### 2) Relay service responsibilities
- poll NEW rows (batch)
- publish to Kafka topic by event_type mapping
- publish 성공 시 SENT + sent_at 업데이트
- 실패 시 FAILED + retry 정책
- 장기 FAILED는 DLQ로 라우팅(또는 ops_task 생성)

### 3) Polling 전략(권장)
- 방식 A: scheduled poll (e.g., 200ms~1s)
- select ... for update skip locked (가능한 DB면)
- batch size: 100~1000
- ordering: created_at asc

### 4) Idempotency
- producer side: dedup_key unique로 중복 insert 방지
- consumer side: event_id or dedup_key로 중복 처리 방지(consumer 가이드 문서화)

### 5) Topic mapping (v1 최소)
- search_impression/click/dwell
- ac_impression/ac_select
- (optional) admin_domain_event / reindex_event / job_run_event

### 6) Operational controls
- metrics + health
- relay lag(NEW backlog) 지표
- pause/resume(옵션): env toggle

## Non-goals
- Schema Registry(Avro/Proto)는 I-0330에서
- Exactly-once semantics 완전 보장은 아님

## DoD
- Relay가 outbox_event를 Kafka로 전송하고 SENT 마킹
- 실패 시 retry/backoff 수행
- backlog/lag/throughput/err metrics 존재
- 중복 insert/중복 publish 상황에서 멱등적으로 안전

## Observability
- metrics:
  - outbox_new_count, outbox_failed_count
  - outbox_publish_total{status}
  - outbox_relay_lag_seconds
- logs:
  - event_id, event_type, dedup_key, kafka_topic, error, request_id/trace_id (있으면)

## Codex Prompt
Build Outbox Relay:
- Read outbox_event(status=NEW) in batches and publish to Kafka topics.
- On success mark SENT with sent_at; on failure mark FAILED and retry with backoff.
- Add metrics for lag, throughput, failure counts and a simple health endpoint.
- Provide consumer idempotency guidance (dedup_key usage) in docs.
