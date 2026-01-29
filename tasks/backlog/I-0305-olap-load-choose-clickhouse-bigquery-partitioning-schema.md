# I-0305 — OLAP load (ClickHouse/BigQuery stack1) + schema/party

## Goal
Search/Autocomplete/Chat/Commercial Events Loading on OLAP
New *CTR/Popularity, LTR learning data, and offline evaluation**.

## Why
- LTR/Recommended/Quality assessment is only possible with “Log-based”
- Analysis/Backfill/Return Strength → OLAP Needs Only Kafka

## Scope
### 1) Select a repository (v1)
- ClickHouse
- prod alternative: BigQuery(optional)

### 2) Event schema(v1)
Basic table (with side/line):
- New  TBD  
- `click`
- `dwell`
- `ac_impression`
- `ac_select`
- (optional)   TBD  ,   TBD   
- (Optional)   TBD   (Commerce)

Required column example:
- `event_time`, `event_type`
- `request_id`, `trace_id`, `session_id`, `user_id_hash`
- New  TBD  ,   TBD  (Optional: Personal Information Issue)
- `imp_id`, `doc_id`, `position`
- `policy_id`, `experiment_id`, `variant`

### 3) Loading system
- ClickHouse insert
- v2: Kafka Connect/CDC (Optional)

### 4) Partition/TTL
- partition: day(event time)
- TTL: 90~180days
- dedup:   TBD   Based upsert/replace strategy (according to the engine selection)

### 5) Data quality check (simplified)
- late arrival
- Event room/recovery detection indicator (count comparison)

## Non-goals
- Full Data Lake / Catalog / Lineage (Extra)
- BI Altitude (Meta Bass I-0306)

## DoD
- ClickHouse(or BigQuery)
- Kafka→OLAP loaded continuous operation (including ground/air monitoring)
- Partition/TTL/Uniform prevention strategy documenting
- Query for LTR (e.g. join for creating labels)

## Codex Prompt
Add OLAP storage & ingestion:
- Stand up ClickHouse (preferred) and create event schemas with partitions/TTL.
- Implement Kafka consumer ingestion with buffering and dedup strategy.
- Document schema, retention, and example analytical queries for LTR/eval.
- Validate by producing sample events and confirming OLAP counts match.
