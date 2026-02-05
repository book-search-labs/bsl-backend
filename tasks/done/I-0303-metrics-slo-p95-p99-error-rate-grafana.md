# I-0303 — Metrics(SLO: p95/p99, error rate) + Grafana dashboards

## Goal
핵심 SLO를 메트릭으로 정의하고,
Grafana 대시보드로 **latency(p50/p95/p99), error rate, throughput, degrade rate, cost proxy**를 상시 확인 가능하게 만든다.

## Why
- trace는 “원인 분석”, metrics는 “상시 감시/경보”에 필수
- 검색/자동완성/챗/리랭킹은 비용/성능 trade-off가 커서 지표가 없으면 망함

## Scope
### 1) 핵심 지표 정의(서비스 공통)
- Request:
  - `http_server_requests_seconds` (p50/p95/p99)
  - `http_requests_total` by status
- Error:
  - 5xx rate, timeout rate, circuit_open rate
- Degrade:
  - `search_degrade_total{reason=...}`
  - `rerank_skipped_total`
  - `vector_disabled_total`
- Budget/Cost proxy(B-0306 연계):
  - `llm_calls_total`, `llm_tokens_total`
  - `mis_infer_requests_total`, batch_size histogram
- Kafka/Outbox:
  - outbox lag, consumer lag, DLQ count

### 2) Exporter/Stack
- Prometheus scraping
- Grafana dashboards
- (선택) Alertmanager 알림

### 3) 대시보드 구성(최소)
- Overview: 전체 트래픽/에러/지연
- Search pipeline: BM25/knn/rerank stage latency(가능하면 custom metrics)
- Autocomplete: Redis hit rate, p99, select rate
- MIS: queue depth, batch size, timeout rate
- Kafka: lag/DLQ
- Cost: LLM tokens, rerank call rate

## Non-goals
- 완전한 SRE 수준 알림 튜닝(초기엔 핵심 경보만)
- 장기 보관/리텐션 최적화(추후)

## DoD
- Prometheus/Grafana가 로컬(또는 stage)에서 동작
- 최소 4개 대시보드(Overview/Search/AC/MIS-Kafka)가 준비됨
- p95/p99, error rate, degrade rate를 한눈에 확인 가능
- 기본 알림(예: 5xx 급증, p99 급증, consumer lag)이 동작(선택)

## Codex Prompt
Implement metrics + dashboards:
- Add Prometheus metrics across services, including degrade/budget/cost proxy counters.
- Provide Prometheus + Grafana docker-compose and importable dashboards.
- Define SLO targets and basic alerts for latency, error rate, and Kafka lag.
- Validate metrics by generating test traffic and confirming dashboards update.
