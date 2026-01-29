# B-0222 — Canonical ETL Idempotent Incremental Upsert (payload_hash)

## Goal
Raw → Canonical Transformation Pipeline ** Fix the file + test (upsert)**.
- The same placement should be the same as multiple times returning.
- Change raw only canonical should be reflected (minimum processing)
- It should be stable in large capacity and “medium/refundable”

## Background
- In operation, canonical loading in B-0221:
  - Resilient/Reliable/Partial failure occur every day
  - “Full playability” is too expensive
- So payload hash-based changes need

## Scope
### 1) payload hash calculation rules confirmed
- raw node.payload(JSON) canonicalize(Line/Remove) after SHA-256
- Year by entity:
  - raw_node(payload_hash)
  - canonical row(source hash) save

### 2) Change detection
- raw node(node id) standard:
  - New: insert
  - Original: payload hash otherwise update
  - skip
- Batch 0

### 3 years ) Standardization of Upsert Method
- MySQL: `INSERT ... ON DUPLICATE KEY UPDATE`
- Tag:
  - canonical payload fields
  - source_hash
  - updated_at
- Soft-delete option (optional) in v1

### 4) Checkpoint / resume
- ingest_checkpoint:
  - last_processed_node_id or last_offset
  - batch_id, entity_kind, processed_count
- Reopening after checkpoint

## Non-goals
- Switch to full CDC (binary log-based)
- Multi-Source Integration (Extra)

## Data Model impact (suggested)
- canonical tables: add `source_hash CHAR(64)` + `updated_at`
- ingest_checkpoint(entity_kind, cursor, batch_id, updated_at)

## Commands / Validation
- The same placement 2 times run → canonical row count/updated at change is "change only"
- Random Sample 1k:
  - raw payload hash == canonical source hash check

## Observability
- metrics:
  - etl_processed_total
  - etl_inserted_total
  - etl_updated_total
  - etl_skipped_total
  - etl_duration_ms
- logs:
  - batch_id, entity_kind, cursor range, error samples

## DoD
- Same as the result when the same input is reissued (left)
- Change raw canonical update
- checkpoint-based
- Performance: Activating at least “full contrast ratio”

## Codex Prompt
Implement canonical ETL incremental upsert:
- compute payload_hash (stable canonicalization + sha256)
- detect changes vs canonical source_hash
- upsert only changed/new records
- persist checkpoints for resume
- add metrics/logging and deterministic DoD checks
