# B-0232 — Emit Search Events (search_impression / click / dwell) for Ranking/LTR Loop

## Goal
For search quality (LTR/CTR/feature) operating loops
Search Results Exposure/Click/Registration Event** Issues as standard skim.

- event types: `search_impression`, `click`, `dwell`
-  TBD   (impression id)
- experiment/policy/model version

## Background
- LTR/Offline assessment/Online indicators are based on event quality.
- In particular, if there is no position bias/session/skill bucket information, the learning is broken.

## Scope
### 1) Event schema (v1 minimum)
#### search_impression
- At the time of occurrence: SERP response downtime
- fields:
  - `event_type`: "search_impression"
  - `event_time`
  - `imp_id` (uuid)
  - `request_id`, `trace_id`, `session_id`, `user_id`(optional)
  - `query`: { `q_raw`, `q_norm`, `q_hash` }
  - `filters`, `sort`, `page`, `size`
  - `results`: [{ `doc_id`, `position`, `score`(optional), `source`(bm25/hybrid), `debug`(optional) }]
  - `pipeline`: { `retrieval`, `fusion`, `rerank`, `model_version` }
  - `experiment`: { `bucket`, `flags` }

#### click
- At the time of occurrence: click the result (incoming details)
- fields:
  - `event_type`: "click"
  - `event_time`
  - `imp_id`
  - `doc_id`, `position`
  - `request_id`, `trace_id`, `session_id`, `user_id`
  - (Optional)   TBD : "serp"

#### dwell
- At the time of occurrence: after a certain period of stay (or unloading page)
- fields:
  - `event_type`: "dwell"
  - `event_time`
  - `imp_id`
  - `doc_id`
  - `dwell_ms`
  - `request_id`, `trace_id`, `session_id`, `user_id`

### 2) Producer location (recommended)
- New *BFF** has external traffic:
  - New  TBD  : BFF records outbox after receiving SR response
  - New  TBD  : Front transfer to BFF endpoint → outbox record
- BFF is not created inside the search service, but the principle of “Single Entry Point”

### 3) imp id creation rules
- 1 Created every search request
- down with imp id in response results,
Click/dwell Delivery to clients that can be included on request

### 4) dedup_key (outbox idempotency)
- `search_impression`: hash(event_type + imp_id)
- `click`: hash(event_type + imp_id + doc_id)
- `dwell`: hash(event_type + imp_id + doc_id + dwell_bucket)
  - dwell ms are volatible → bucketize recommended (e.g. 0-5s/5-30s/30s+)

## Non-goals
- OLAP Loading(=I-0305)
- Create learning labels(=B-0290)
- outbox relay(=B-0248)

## DoD
- search impression/click/dwell outbox event
- including imp id, position, query hash, pipeline/experiment information on payload
- dedup key
- verification of “impression → click → dwell” connection with sample logs

## Observability
- metrics:
  - search_impression_total, click_total, dwell_total
  - click_through_rate_proxy, avg_dwell_ms_proxy
- tracing:
  - connection to SR/QS/RS/MIS with request id/trace id (reverse)

## Codex Prompt
Add search event emission for ranking/LTR:
- Define v1 schemas for search_impression/click/dwell including imp_id, positions, query_hash, pipeline and experiment metadata.
- Emit events via outbox_event from BFF (search response + client callbacks).
- Implement deterministic dedup_key rules.
- Provide smoke tests verifying the event chain (impression->click->dwell) is joinable.
