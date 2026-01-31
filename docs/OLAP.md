# OLAP (ClickHouse) — Events & Labels

## Choice
**ClickHouse** is the default OLAP store for dev/stage. It supports fast inserts and
partitioned analytical queries for CTR/Popularity and LTR labeling.

## Schema & Retention
Schema lives in `infra/clickhouse/init.sql`.

Tables are partitioned by `event_date` and use `ReplacingMergeTree` with TTL:
- Search/AC events: 180 days
- Purchases: 365 days

Primary tables:
- `search_impression`
- `search_click`
- `search_dwell`
- `ac_impression`
- `ac_select`
- `ltr_training_example`
- `add_to_cart` (placeholder)
- `purchase` (placeholder)

## Ingestion Path (v1)
```
Outbox → Kafka → olap-loader-service → ClickHouse
```

The loader consumes topics:
`search_impression_v1`, `search_click_v1`, `search_dwell_v1`, `ac_impression_v1`, `ac_select_v1`
and inserts JSONEachRow into ClickHouse.

## Label Generation (B-0290)
Use `scripts/olap/generate_ltr_labels.py` to produce `ltr_training_example`.

Example:
```bash
python scripts/olap/generate_ltr_labels.py \
  --start-date 2026-01-30 \
  --end-date 2026-01-31 \
  --dwell-ms 30000 \
  --max-negatives 100 \
  --bucket explore
```

The job:
- drops existing partitions (idempotent)
- inserts labels 0–4 using click/dwell/cart/purchase rules
- prints basic data quality checks (label distribution, bucket counts)

## Position Bias (B-0291)
Search Service assigns `experiment_bucket` (`control`/`explore`) and shuffles a safe
rank window for the explore bucket. The bucket is stored in `search_impression` and
propagated to `ltr_training_example` for offline filtering or weighting.
