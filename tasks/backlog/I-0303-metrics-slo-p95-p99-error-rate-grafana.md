# I-0303 — Metrics(SLO: p95/p99, error rate) + Grafana dashboards

## Goal
define the core SLO as metric,
The Grafana dashboard allows you to check latency (p50/p95/p99), error rate, throughput, degrade rate, cost proxy**.

## Why
- trace is essential for “original analysis”, metrics “emergency monitoring/watching”
- Search/Autocomplete/Chat/Reranking cost/Performance trade-off is not a cursor indicator

## Scope
### 1) Core indicator definition (service common)
- Request:
  - `http_server_requests_seconds` (p50/p95/p99)
  - `http_requests_total` by status
- Error:
  - 5xx rate, timeout rate, circuit_open rate
- Degrade:
  - `search_degrade_total{reason=...}`
  - `rerank_skipped_total`
  - `vector_disabled_total`
- Budget/Cost proxy(B-0306):
  - `llm_calls_total`, `llm_tokens_total`
  - `mis_infer_requests_total`, batch_size histogram
- Kafka/Outbox:
  - outbox lag, consumer lag, DLQ count

### 2) Exporter/Stack
- Prometheus scraping
- Grafana dashboards
- Alertmanager

### 3) Dashboard configuration (minimum)
- Overview: Full Traffic / Error / Open
- BM25/Kn/rerank stage latency (custom metrics available)
- Autocomplete: Redis hit rate, p99, select rate
- MIS: queue depth, batch size, timeout rate
- Kafka: lag/DLQ
- Cost: LLM tokens, rerank call rate

## Non-goals
- Complete SRE level notification tuning (only key alarms)
- Long-term storage/retainment optimization (after)

## DoD
- Prometheus/Grafana runs on local (or stage)
- The minimum of 4 Dashboard (Overview/Search/AC/MIS-Kafka) is ready
- p95/p99, error rate, degrade rate at a glance
- Basic reminder (e.g. 5xx reinforcement, p99 reinforcement, consumer lag)

## Codex Prompt
Implement metrics + dashboards:
- Add Prometheus metrics across services, including degrade/budget/cost proxy counters.
- Provide Prometheus + Grafana docker-compose and importable dashboards.
- Define SLO targets and basic alerts for latency, error rate, and Kafka lag.
- Validate metrics by generating test traffic and confirming dashboards update.
