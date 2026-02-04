# ClickHouse (OLAP) — Local Setup

This directory contains the ClickHouse bootstrap schema for OLAP ingestion.

## Tables
- `search_impression`
- `search_click`
- `search_dwell`
- `ac_impression`
- `ac_select`
- `chat_sessions`
- `chat_turns`
- `chat_feedbacks`
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

## Chat quality report queries (examples)

Top queries with the highest negative feedback ratio:

```sql
SELECT
  s.canonical_key,
  count() AS feedback_count,
  sum(f.rating = 'down') AS thumbs_down,
  round(thumbs_down / feedback_count, 4) AS thumbs_down_ratio
FROM bsl_olap.chat_feedbacks f
LEFT JOIN bsl_olap.chat_sessions s
  ON f.conversation_id = s.conversation_id AND f.turn_id = s.turn_id
WHERE f.event_date >= today() - 7
GROUP BY s.canonical_key
HAVING feedback_count >= 5
ORDER BY thumbs_down_ratio DESC
LIMIT 20;
```

Fallback ratio caused by citation failures:

```sql
SELECT
  round(sum(status = 'insufficient_evidence') / count(), 4) AS insufficient_ratio
FROM bsl_olap.chat_turns
WHERE event_date >= today() - 7;
```
