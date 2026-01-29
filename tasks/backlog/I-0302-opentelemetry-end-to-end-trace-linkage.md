# I-0302 — OpenTelemetry end-to-end(trace connection)

## Goal
BFF → QS → SR → RS/MIS → OpenSearch/DB/Kafka
p95/p99 creates “on one time” tracking for delays and failure causes.

## Why
- Unable to operate without observing the multi-service structure
- Especially hybrid/rerank/LLM phase is required by bottlenecks often → trace

## Scope
### 1) Trace context standard
- New  TBD  ,   TBD  ,   TBD 
- Payment Terms:
  - HTTP: W3C Trace Context(`traceparent`) + `x-request-id`
  - Kafka: with trace context on message headers

### 2) Instrumentation
- Spring Boot(BFF/SR/AC):
  - OTel Java Agent or SDK Instrumentation
- FastAPI(QS):
  - OTel Python instrumentation
- MIS:
  - OTel Python
- OpenSearch/DB client span included (available range)

### 3) Collector/Backend
- OTel Collector + Jaeger/Tempo
- Metrics

### 4) Trace sampling
- dev: 100%
- stage/prod: head-based + error/slow return priority (e.g. tail sampling options)

## Non-goals
- Full log correlation (Log pipeline I-0304)
- APM Commercial Tool Integration (Optional)

## DoD
- BFF→QS→SR→MIS
- Kafka event also leads to trace (transfer producer→consumer connection)
- p99 slow section can be identified as span
- Sampling/PII Policy Default Documentation

## Codex Prompt
Add end-to-end OpenTelemetry:
- Standardize request_id and W3C trace propagation across HTTP and Kafka.
- Instrument BFF/SR/AC (Java) and QS/MIS (Python) with OTel.
- Provide local collector + tracing backend setup and sampling configuration.
- Validate with a demo trace spanning all services and dependencies.
