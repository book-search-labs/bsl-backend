# B-0248 — Outbox → Kafka Relay (Idempotent, Retry-safe)

## Goal
The event that occurred in the service is recorded in the **DB Outbox**, and the relay will be sent to **Kafka to secure**.

- Transfer(dedup key)
- Rehabilitation/Disability Recovery
- DLQ/Reprocessing (Connect with Infra Ticket)
- Minimum “exactly-once” operation (consumer idem home)

## Background
- When Kafka publish in serving request:
  - publish Failure/Duplication/Purpose problem in operation of hell.
- The Outbox pattern guarantees “Event Records in DB Transactions”.

## Scope
### 1) DB (already exists)
New  TBD   Table Use:
- dedup_key NOT NULL + UNIQUE
- status: NEW/SENT/FAILED
- sent at history

### 2) Relay service responsibilities
- poll NEW rows (batch)
- publish to Kafka topic by event_type mapping
- SENT + sent at update when publish success
- FAILED + retry policy at failure
- Long term FAILED routes to DLQ (or generate ops task)

### 3 years ) Polling Strategy
- (e.g., 200ms~1s)
- select ... for update skip locked (Dependable DB)
- batch size: 100~1000
- ordering: created_at asc

### 4) Idempotency
- dedup key unique
- consumer side: event id or dedup key

### 5 days Topic mapping
- search_impression/click/dwell
- ac_impression/ac_select
- (optional) admin_domain_event / reindex_event / job_run_event

### 6) Operational controls
- metrics + health
- relay lag(NEW backlog) indicator
- pause/resume(optional): env toggle

## Non-goals
- Schema Registry (Avro/Proto) from I-0330
- Exactly -once semantics full warranty

## DoD
- Send outbox event to Kafka and print SENT
- retry/backoff
- backlog/lag/throughput/err metrics presence
- publish publish publish publish publish

## Observability
- metrics:
  - outbox_new_count, outbox_failed_count
  - outbox_publish_total{status}
  - outbox_relay_lag_seconds
- logs:
  - event id, event type, dedup key, kafka topic, error, request id/trace id

## Codex Prompt
Build Outbox Relay:
- Read outbox_event(status=NEW) in batches and publish to Kafka topics.
- On success mark SENT with sent_at; on failure mark FAILED and retry with backoff.
- Add metrics for lag, throughput, failure counts and a simple health endpoint.
- Provide consumer idempotency guidance (dedup_key usage) in docs.
