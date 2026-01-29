# I-0302 — OpenTelemetry end-to-end(trace 연결)

## Goal
BFF → QS → SR → RS/MIS → OpenSearch/DB/Kafka 까지 **단일 trace로 연결**해서,
p95/p99 지연과 장애 원인을 “한 번에” 추적 가능하게 만든다.

## Why
- 멀티 서비스 구조에서 관측 없으면 운영 불가능
- 특히 hybrid/rerank/LLM 단계는 병목이 자주 생김 → trace가 필수

## Scope
### 1) Trace context 표준
- `trace_id`, `span_id`, `request_id` 규칙 확정
- 전파 방식:
  - HTTP: W3C Trace Context(`traceparent`) + `x-request-id`
  - Kafka: message headers에 trace context 포함

### 2) Instrumentation
- Spring Boot(BFF/SR/AC):
  - OTel Java agent 또는 SDK instrumentation
- FastAPI(QS):
  - OTel Python instrumentation
- MIS:
  - OTel Python(또는 whichever runtime) instrumentation
- OpenSearch/DB client span 포함(가능한 범위)

### 3) Collector/Backend
- Local: OTel Collector + Jaeger/Tempo 중 택1
- Metrics와 연계(I-0303)

### 4) Trace sampling
- dev: 100%
- stage/prod: head-based + 오류/슬로우 리퀘스트 우선(예: tail sampling 옵션)

## Non-goals
- 완전한 로그 상관관계(로그 파이프라인은 I-0304)
- APM 상용툴 통합(선택)

## DoD
- 검색 요청 1건이 BFF→QS→SR→MIS까지 하나의 trace로 보임
- Kafka 이벤트에도 trace가 이어짐(적어도 producer→consumer 연결)
- p99 느린 구간이 span으로 식별 가능
- 샘플링/PII 정책 기본값 문서화

## Codex Prompt
Add end-to-end OpenTelemetry:
- Standardize request_id and W3C trace propagation across HTTP and Kafka.
- Instrument BFF/SR/AC (Java) and QS/MIS (Python) with OTel.
- Provide local collector + tracing backend setup and sampling configuration.
- Validate with a demo trace spanning all services and dependencies.
