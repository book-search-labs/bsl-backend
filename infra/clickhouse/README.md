# ClickHouse (OLAP) — Local Setup

This directory contains the ClickHouse bootstrap schema for OLAP ingestion.

## Tables
- `search_impression`
- `search_click`
- `search_dwell`
- `ac_impression`
- `ac_select`
- `feat_doc_daily`
- `feat_qd_daily`
- `ltr_training_example`

All tables are partitioned by `event_date` and use `ReplacingMergeTree` with a
`TTL event_date + INTERVAL 180 DAY` retention policy.

## Docker Compose
`compose.yaml` mounts `infra/clickhouse/init.sql` into `/docker-entrypoint-initdb.d/`.

## Notes
- Dedup is handled by `ReplacingMergeTree` using `(event_date, dedup_key, doc_id)` order.
- For replays, use partition drops in `ltr_training_example` before inserts.
