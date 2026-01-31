CREATE DATABASE IF NOT EXISTS bsl_olap;

CREATE TABLE IF NOT EXISTS bsl_olap.search_impression (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    session_id Nullable(String),
    user_id_hash Nullable(String),
    query_hash Nullable(String),
    query_raw Nullable(String),
    imp_id String,
    doc_id String,
    position UInt16,
    policy_id Nullable(String),
    experiment_id Nullable(String),
    experiment_bucket Nullable(String),
    source Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, doc_id)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.search_click (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    session_id Nullable(String),
    user_id_hash Nullable(String),
    query_hash Nullable(String),
    imp_id String,
    doc_id String,
    position UInt16,
    policy_id Nullable(String),
    experiment_id Nullable(String),
    experiment_bucket Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, doc_id)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.search_dwell (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    session_id Nullable(String),
    user_id_hash Nullable(String),
    query_hash Nullable(String),
    imp_id String,
    doc_id String,
    position UInt16,
    dwell_ms UInt32,
    policy_id Nullable(String),
    experiment_id Nullable(String),
    experiment_bucket Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, doc_id)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.ac_impression (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    q String,
    size UInt16,
    count UInt16,
    text String,
    position UInt16,
    suggest_id Nullable(String),
    type Nullable(String),
    source Nullable(String),
    target_id Nullable(String),
    target_doc_id Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, position)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.ac_select (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    q String,
    text String,
    position UInt16,
    suggest_id Nullable(String),
    type Nullable(String),
    source Nullable(String),
    target_id Nullable(String),
    target_doc_id Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, position)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.ltr_training_example (
    event_date Date,
    event_time DateTime,
    query_hash String,
    doc_id String,
    label UInt8,
    position UInt16,
    imp_id String,
    request_id String,
    trace_id String,
    policy_id Nullable(String),
    experiment_id Nullable(String),
    experiment_bucket Nullable(String),
    feature_snapshot_date Date,
    position_weight Float32,
    dwell_ms Nullable(UInt32),
    generated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(generated_at)
PARTITION BY event_date
ORDER BY (event_date, imp_id, doc_id);

CREATE TABLE IF NOT EXISTS bsl_olap.add_to_cart (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    session_id Nullable(String),
    user_id_hash Nullable(String),
    doc_id String,
    order_id Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, doc_id)
TTL event_date + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS bsl_olap.purchase (
    event_date Date,
    event_time DateTime,
    event_id String,
    dedup_key String,
    request_id String,
    trace_id String,
    session_id Nullable(String),
    user_id_hash Nullable(String),
    doc_id String,
    order_id Nullable(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(event_time)
PARTITION BY event_date
ORDER BY (event_date, dedup_key, doc_id)
TTL event_date + INTERVAL 365 DAY;
