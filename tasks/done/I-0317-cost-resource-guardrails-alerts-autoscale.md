# I-0317 — 비용/리소스 가드레일 (알람/오토스케일 정책)

## Goal
서비스 운영 비용과 리소스를 “의도적으로” 통제한다.
- 트래픽 급증/봇/비정상 쿼리로 인한 **비용 폭발 방지**
- p95/p99 악화 전에 **알람 + 자동 완화(degrade)**

## Why
- 검색/리랭킹/LLM/RAG는 호출량이 곧 비용
- OpenSearch/Kafka/OLAP는 스토리지/컴퓨트가 선형으로 증가
- “예산” 없으면 운영이 아니라 도박이 됨

## Scope
### 1) 비용/리소스 KPI 정의
- API별 RPS / 에러율 / p95,p99
- OpenSearch: CPU, JVM heap, search latency, indexing rate, segment/merge pressure, disk usage
- Kafka: consumer lag, DLQ rate, outbox backlog
- MIS: QPS, queue depth, batch size, latency, CPU/GPU util
- LLM: requests/day, tokens/day, $/day(가능하면)

### 2) Guardrail 정책(필수)
- Rate limit 정책(B-0227 연계) + burst/봇 차단
- Query cost governor(서비스별):
  - QS 2-pass 호출 비율 상한
  - SR hybrid(벡터) 호출 비율 상한
  - RS rerank topR 상한, timeout budget
  - (RAG) max_context_chunks, max_tokens 상한
- 자동 완화(degrade) 토글:
  - rerank off → fusion 결과 사용
  - vector off → bm25-only
  - QS 2-pass off → 1-pass only
  - chat “citations-only / refuse” 모드

### 3) 알람/대시보드 연결
- Grafana alert rule 세트(연계: I-0303)
- “운영 토글” 문서화(연계: I-0316 Runbook)

### 4) 오토스케일 기준(초기)
- HPA/오토스케일: CPU, p95 latency, queue depth(MIS), consumer lag(Kafka)
- 최소/최대 replica, cooldown

## Non-goals
- FinOps 수준의 예산 청구/태깅 자동화(추후)

## DoD
- Guardrail 지표/알람이 “작동”하고, 알람 발생 시 즉시 완화 방법이 Runbook에 있음
- (가능하면) load test에서 degrade 토글이 실제로 비용/지연을 낮춤

## Codex Prompt
Implement cost/resource guardrails:
- Define key metrics and alert rules for each service (BFF/QS/SR/RS/MIS/OS/Kafka).
- Add runtime toggles for degrade modes (rerank/hybrid/2-pass/chat budgets).
- Document actions in runbook and validate with a basic load scenario.
