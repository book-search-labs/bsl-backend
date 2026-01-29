# I-0317 — Cost/Resort Gadle (Alam/Otoscape Policy)

## Goal
We use cookies to ensure that we give you the best experience on our website.
- Anti-explosion of costs due to traffic rapids/bots/defection queries**
- p95/p99 Before deterioration**Arram + Auto mitigation(degrade)* News

## Why
- Search/Licing/LLM/RAG calls are soon cost
- OpenSearch/Kafka/OLAP increases storage/comput linearly
- If there is no operation without "experience", it becomes gambling

## Scope
### 1) Cost/Resource KPI definition
- API RPS / Error Rate / p95,p99
- OpenSearch: CPU, JVM heap, search latency, indexing rate, segment/merge pressure, disk usage
- Kafka: consumer lag, DLQ rate, outbox backlog
- MIS: QPS, queue depth, batch size, latency, CPU/GPU util
- LLM: request/day, token/day, $/day

### 2) Guardrail Policy (required)
- Rate limit policy (B-0227 linkage) + burst/bot blocking
- Query cost governor:
  - QS 2-pass call rate upper
  - SR hybrid(Battery) call rate upper
  - RS rerank topR high end, timeout budget
  - (RAG) max context chunks, max tokens upper
- Automatic Winding (degrade) Toggle:
  - rerank off → use fusion results
  - vector off → bm25-only
  - QS 2-pass off → 1-pass only
  - "citations-only" mode

### 3) Alarm/Dashboard connection
- Grafana alert rule set (banner: I-0303)
- <# if ( data.meta.album ) { #>{{ data.meta.album }}<# } #> <# if ( data.meta.artist ) { #>{{ data.meta.artist }}<# } #>

### 4) Autoscale Standard (Ultrasonic)
- HPA/Otosuke: CPU, p95 latency, queue depth(MIS), consumer lag(Kafka)
- minimal/ replica, cooldown

## Non-goals
- FinOps level budget billing/tagging automation (extra)

## DoD
- Guardrail indicators/alamings are “operation” and immediately mitigating method when alarm occurs in Runbook
- (when possible) degrade toggle in load test is actually low cost/start

## Codex Prompt
Implement cost/resource guardrails:
- Define key metrics and alert rules for each service (BFF/QS/SR/RS/MIS/OS/Kafka).
- Add runtime toggles for degrade modes (rerank/hybrid/2-pass/chat budgets).
- Document actions in runbook and validate with a basic load scenario.
