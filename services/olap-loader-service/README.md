# OLAP Loader Service

Consumes Kafka events and inserts into ClickHouse (JSONEachRow).

## Run
```bash
cd services/olap-loader-service
./gradlew bootRun
```

## Config
- `KAFKA_BOOTSTRAP_SERVERS` (default: `localhost:9092`)
- `CLICKHOUSE_URL` (default: `http://localhost:8123`)
- `CLICKHOUSE_DB` (default: `bsl_olap`)
- `CLICKHOUSE_BATCH_SIZE` (default: `200`)
- `CLICKHOUSE_FLUSH_MS` (default: `1000`)

## Topics
Configured under `olap.topics.*` in `application.yml`:
`search_impression_v1`, `search_click_v1`, `search_dwell_v1`, `ac_impression_v1`, `ac_select_v1`.
