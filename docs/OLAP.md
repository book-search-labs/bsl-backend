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
- `search_result_summary`
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
`search_impression_v1`, `search_result_summary_v1`, `search_click_v1`, `search_dwell_v1`, `ac_impression_v1`, `ac_select_v1`
and inserts JSONEachRow into ClickHouse.

## Feature Aggregation (B-0292)
Use `scripts/olap/aggregate_features.py` to compute CTR/Popularity with smoothing + decay:

```bash
python scripts/olap/aggregate_features.py \
  --start-date 2026-01-30 \
  --end-date 2026-01-31 \
  --half-life-days 14 \
  --alpha 1.0 \
  --beta 20.0
```

This generates:
- `feat_doc_daily` (doc-level CTR/popularity snapshots)
- `feat_qd_daily` (query-doc CTR snapshots)
- updates `config/feature_store.json` with latest doc features

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
- uses `query_hash` as join key (raw query text is not required for training joins)

## Point-in-time correctness (B-0293)
Snapshots live in `feat_doc_daily` / `feat_qd_daily`. Join training examples on
`feature_snapshot_date = event_date` to avoid leakage.

Validation helper:
```bash
python scripts/olap/validate_feature_snapshot.py --date 2026-01-31
```

Build training dataset with time-join:
```bash
python scripts/olap/build_training_dataset.py --start-date 2026-01-30 --end-date 2026-01-31 --output /tmp/ltr.jsonl
```

## Position Bias (B-0291)
Search Service assigns `experiment_bucket` (`control`/`explore`) and shuffles a safe
rank window for the explore bucket. The bucket is stored in `search_impression` and
propagated to `ltr_training_example` for offline filtering or weighting.
