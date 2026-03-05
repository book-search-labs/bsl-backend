# OpenSearch Sync Events (MySQL -> OpenSearch)

## 1) Standard event types

- `material.upsert_requested`
- `material.delete_requested`

Payload contract (v1):
- `contracts/events/material.upsert_requested.v1.json`
- `contracts/events/material.delete_requested.v1.json`

Both payloads carry only `material_id` as projection target.

## 2) Topic / Key / Ordering

- Topic: `os.sync.material.v1`
- Kafka record key: `material_id`
- Ordering rule: all events for the same `material_id` must stay in the same partition.

## 3) Outbox contract

Outbox table: `outbox_event`

Required columns:
- `event_id` (monotonic PK)
- `event_type`
- `aggregate_type`
- `aggregate_id`
- `payload_json`
- `occurred_at`
- `status` (`NEW|PUBLISHED|FAILED`)
- `published_at`
- `retry_count`
- `last_error`
- `dedup_key` (unique)

Dedup key rule:
- `dedup_key = sha256(event_type + ":" + material_id + ":" + version)`
- `version` can use source change version (`raw_id`, `row_version`) and may fall back to `outbox.event_id` when needed.

## 4) Relay behavior

- Relay reads `outbox_event.status = NEW` in ascending `event_id`
- Publish to `os.sync.material.v1`
- On success: mark `PUBLISHED`, set `published_at`
- On failure: increment `retry_count`, store `last_error`
- Retry exhaustion: mark `FAILED` and route to `<topic>.dlq`

## 5) Consumer behavior

- Consumer resolves current material state from MySQL by `material_id`
- `material.upsert_requested`: rebuild projection document and OpenSearch upsert
- `material.delete_requested`: OpenSearch delete (or tombstone policy)
- Idempotency: `processed_event(event_id, handler)` stores handled events

## 6) Reconcile / Repair

- Reconciler compares MySQL `updated_at` vs OpenSearch document freshness
- Drifted/missing doc: re-enqueue `material.upsert_requested`
- Deleted material: enqueue `material.delete_requested`
- Requeue path is always `outbox_event` (single standard write path)

## 7) Ops checks

- Lag: oldest `NEW` outbox event age (`os_sync_lag_seconds`)
- Throughput: processed totals by event type
- Failures / DLQ counts and latest errors
- Replay: reset failed outbox rows to `NEW` for controlled re-publish
