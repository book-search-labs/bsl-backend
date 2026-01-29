# I-0330 — Kafka schema strategy (Avro/Protobuf) + compatibility rules + DLQ/Replay

## Goal
Kafka event is standardized in “operable” form:
- Schema version/Compatibility
- DLQ/Replay
- Venues   Venues

## Why
- The event will cause the “previous message” to fail
- By expanding to AC/Ranking/Chat/Commerce, you’ll be unconditional without schema management

## Scope
### 1) Select schema format
- Avro + Schema Registry
- Tag:
  - schema_version
  - event_id / dedup_key
  - occurred_at
  - producer/service name

### 2) compatibility rules (min.)
- backward compatible
- Breaking change prohibited (field deletion/replacement etc.)
- Optional Field Addition Acceptable
- enum extensions define rules

### 3) DLQ
- consumer failure:
  - backoff
  - Go to DLQ Topics
- Error Cause/Stack/Original Offset Record on DLQ message

### 4) Replay/Replayer
- Reprocessing tool for setting / offset range
- “Floor Treatment” prerequisite:
  - outbox event.dedup key

### 5) Document/Guide
- Event Type List:
  - search_impression/click/dwell
  - ac_impression/ac_select
  - chat_feedback
  - admin_domain_event(ops/reindex/synonym/merge)
  - commerce events

## Non-goals
- Standardization of complete data platform (KStreams/Flink)

## DoD
- schema file exists for at least 3 event types (contracts/events/)
- Consumers can safely drop and replay with DLQ
- The compatibility rules are documented and checked in CI (if possible)

## Codex Prompt
Define Kafka schema strategy:
- Choose Protobuf or Avro, create versioned schemas for core events.
- Implement DLQ handling and a replay tool.
- Document compatibility rules and enforce basic checks in CI.
