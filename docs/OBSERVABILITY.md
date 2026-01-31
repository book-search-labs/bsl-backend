# Observability (Phase 9)

This document defines the **minimum production observability standard** for BSL.
It covers **tracing, metrics, logs, dashboards, retention**, and **cost guardrails**.

---

## 1) OpenTelemetry (Tracing)

**Goal:** end-to-end trace linkage from Web → BFF → downstream services.

### Trace propagation
- **W3C `traceparent`** is the canonical trace header.
- `x-trace-id` and `x-request-id` remain for compatibility and log correlation.
- BFF generates a valid `traceparent` when missing and forwards it downstream.

### Java services (Spring Boot)
- Enable tracing with `micrometer-tracing-bridge-otel` + OTLP exporter.
- OTLP endpoint defaults to **`http://localhost:4318/v1/traces`**.
- Sampling controlled by `TRACE_SAMPLE_PROBABILITY` (default `1.0`).

### Python services (FastAPI)
- Use **OpenTelemetry auto-instrumentation** when running in stage/prod.
- Example (local):
  ```bash
  pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp \
    opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx

  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  OTEL_SERVICE_NAME=query-service \
  opentelemetry-instrument uvicorn app.main:app --host 0.0.0.0 --port 8001
  ```

---

## 2) Metrics (SLO: p95/p99 + error rate)

### Required metrics
- HTTP latency p95/p99 (by service)
- Error rate (5xx / total)
- Request throughput (RPS)

Spring Boot **Actuator + Prometheus** exposes:
- `/actuator/prometheus`
- `http_server_requests_seconds_*` (histogram)

### Prometheus + Grafana (local)
```bash
./scripts/observability_up.sh
```
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

Dashboard: **BSL Service SLOs** (provisioned).

---

## 3) Logs (Collection / Sampling / Retention)

### Policy (minimum)
- **Structured** log lines with `trace_id`, `request_id`, `service` name
- **Sampling**: allow INFO logs in prod, DEBUG only for short windows
- **Retention**: 7–30 days for infra logs; 30–90 days for audit logs

### Audit logs (admin actions)
- Admin mutations are persisted to `audit_log` (DB).
- Include `actor_admin_id`, action, request/trace IDs, and IP/User-Agent.
- Retain audit logs for **≥ 90 days** in prod.

### Local (optional)
- Loki + Promtail are provided in the observability compose stack.
- Promtail reads Docker container logs at `/var/lib/docker/containers/*/*.log`.

---

## 4) Dashboards & KPIs

### Grafana
- SLO overview (latency + error rate)
- Service RPS by endpoint
- JVM memory + GC (optional)

### Metabase (BI)
- Metabase runs at http://localhost:3001
- Use MySQL / ClickHouse as primary sources

Suggested KPI dashboards:
- Search CTR, 0-result rate, p95 latency
- Autocomplete selection rate
- Order conversion rate, AOV, refund rate
- Inventory out-of-stock rate

---

## 5) Cost & Resource Guardrails

- **Alert** when p99 latency > threshold for 5+ minutes
- **Alert** when error rate > 1% for 5+ minutes
- **Alert** on DB CPU > 80% or disk > 80%
- Limit heavy endpoints via **rate limit** and **timeout budgets**
- Prefer autoscaling based on **RPS + CPU** for stateless services

---

## 6) Quick Reference (Env)

Common:
- `TRACE_SAMPLE_PROBABILITY=1.0`
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces`

Prometheus scrape targets (local):
- `http://localhost:8088/actuator/prometheus` (BFF)
- `http://localhost:8080/actuator/prometheus` (Search)
- `http://localhost:8081/actuator/prometheus` (Autocomplete)
- `http://localhost:8082/actuator/prometheus` (Ranking)
- `http://localhost:8091/actuator/prometheus` (Commerce)
- `http://localhost:8095/actuator/prometheus` (Outbox Relay)
- `http://localhost:8096/actuator/prometheus` (OLAP Loader)
