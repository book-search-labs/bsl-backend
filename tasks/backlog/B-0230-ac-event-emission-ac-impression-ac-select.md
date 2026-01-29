# B-0230 — Emit Autocomplete Events (ac_impression / ac_select) via Outbox → Kafka

## Goal
Autocomplete Use Logs ** Issued as Standard Event**
CTR/Popularity aggregates “operating loop” that leads to the aggregate (=B-0231).

- event types: `ac_impression`, `ac_select`
- Recommended: **BFF recorded on outbox event** → relay sent Kafka (B-0248)
- Event ** dedup key**

## Background
- autocomplete should be clicked/selected data “the system that is good”
- Directly Kafka publish is a big risk of data loss in failure/repair
outbox pattern is operating standard.

## Scope
### 1) Event schema (v1)
#### ac_impression
- At the time of occurrence: short-circuiting of AC response (no exemption)
- payload fields (minimum):
  - `event_type`: "ac_impression"
  - `event_time`
  - New  TBD  ,   TBD  ,   TBD  
  - New  TBD     TBD   (web/mobile/admin)
  - New TBD (Original), TBD (정규화)
  - `candidates`: [{ `suggest_text`, `rank`, `source`(cache/os), `score` }]
  - `policy`: { `cache_hit`, `index_version`, `experiment` }

#### ac_select
- When a user selects a specific suggestion
- payload fields:
  - `event_type`: "ac_select"
  - `event_time`
  - `request_id`, `trace_id`, `session_id`, `user_id`
  - `q_prefix_norm`
  - `selected`: { `suggest_text`, `rank`, `source`, `score` }
  - (Optional)   TBD  : "search submit" | "navigate" etc.

### 2) dedup key rule (left)
- ac_impression:
  - New  TBD   (request id only)
- ac_select:
  - `hash(event_type + request_id + selected.suggest_text)`
- outbox event   TBD  Uniform prevention with UNIQUE

### 3) Producer location (recommended)
- New *BFF**   TBD    Record outbox event while assembly/returning response
- (대안) AC service outbox event record (장 X: dispersion/operation return↑)

### 4) Storage
- New  TBD   Table Use (Imi v1.1 schema exist)
  - status NEW/SENT/FAILED
  - relay handles B-0248 tickets

## Non-goals
- Updates (=B-0231)
- schema registry(=I-0330)
- Click/Change(Search Events) (Other B-0232)

## DoD
- New  TBD   Record ac impression outbox when responding
- When the selected event is passed to BFF, ac select outbox records
- dedup key
- Complete smoke testing with outbox event row in local

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
