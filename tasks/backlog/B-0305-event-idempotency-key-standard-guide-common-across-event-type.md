# B-0305 — Event dedup key standardization guide (all event type common)

## Goal
All events in Outbox→Kafka pipeline
- Safe and secure even when transferring or redundancy
- Conschmer can be handled on the floor
**standardize the dedup key rule.

## Why
- Click/Export/Option/Dwell/Buy Events are retransportable (network, failure, reprocessing)
- CTR/Popularity aggregates if you don't have a load, and the ranking is broken.

## Scope
### 1) Common Event Envelope Specification
- `event_type`
- `event_time` (UTC)
- `request_id`, `trace_id`, `session_id`
- `producer`(service, version)
- `payload`(event specific)
- New  TBD   (Required)

### 2) dedup key creation rules (recommended)
dedup key should represent "the same real world event"**.

- **search_impression**
  - key =   TBD    (imp id is server-generated UUID)
- **click**
  - key = `clk:{imp_id}:{doc_id}:{position}` (+ timestamp bucket optional)
- **dwell**
  - key =   TBD   (dwell is a separate policy)
- **ac_impression**
  - key = `acimp:{ac_req_id}`
- **ac_select**
  - key = `acsel:{ac_req_id}:{selected_text}`

> Warranty:
- "client timestamp" not included**server-issued id**(imp id/ac req id)
- position/Document id Set the same separator as the event unit

### 3) Outbox event table integration
- When BFF/service is stored in outbox event:
  - New  TBD   NOT NULL + UNIQUE Forced (Imi skima available)
- dedup key based on “processing history table” or KV

### 4) Consumer idempotency strategy
- v1:   TBD   table(or Redis set) to save the latest N-day dedup key
- v2: Extendable to true-once (transaction + offsets)

## Non-goals
- Complete EOS (Exactly Once Semantics) Warranty
- About Schema Registry (I Ticket)

## DoD
- dedup key rule documentation for all event type exists
- Producer generates dedup key as the same rule to record in outbox
- Aggregator/Consumer does not occur duplicate aggregates with dedup processing
- Even when replay is reprocessed, the result is stable (no increase in redundancy)

## Codex Prompt
Standardize dedup_key for all events:
- Define a common event envelope including dedup_key and required tracing fields.
- Specify dedup_key formulas per event_type using server-issued ids (imp_id/ac_req_id).
- Ensure producers write outbox_event with UNIQUE(dedup_key) and consumers implement idempotent processing using a dedup store.
- Add documentation and minimal tests showing replay does not inflate aggregates.
