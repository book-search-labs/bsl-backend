# B-0267 — SR Reliability: Circuit Breaker / Timeout / Hedged + Degraded Response(0건 방지)

## Goal
Search Service를 운영형으로 “안 죽게” 만든다.

- stage별 timeout budget 강제(BM25 / embedding / kNN / rerank)
- 서킷브레이커 + bulkhead(동시성 제한)
- hedged request(선택): 느릴 때 보조 경로 실행
- partial failure라도 **best-effort 결과** 반환(0건 방지)
- degrade reason을 응답/로그/이벤트에 기록

## Background
- hybrid 파이프라인은 의존성이 많아 부분 실패가 흔함.
- 운영에서는 “완벽한 결과”보다 “응답을 내고 degrade를 기록”하는게 중요.

## Scope
### 1) Timeout budgets (example defaults)
- bm25: 80~120ms
- embedding: 20~60ms
- knn: 120~200ms
- rerank: 120~250ms
- total: 250~400ms (환경별)

### 2) Circuit breaker + bulkhead
- downstream별:
  - OpenSearch, MIS(embeddings/rerank), RS 등
- 정책:
  - failure rate threshold
  - open state cooldown
  - half-open probes
- bulkhead:
  - 동시 요청 수 제한(큐잉 or fail-fast)

### 3) Degrade rules (must-have)
- vector 단계 실패 → bm25-only
- rerank 실패 → fused order 그대로 반환
- bm25 실패지만 vector 성공 → vector-only(가능하면)
- 둘 다 실패 → 최소 fallback:
  - 최근 인기/트렌드(옵션) or 빈 결과 + “degraded=true” (단, 0건 방지는 가능하면 추천 fallback)

### 4) Hedged request (optional)
- bm25가 timeout nearing이면:
  - simple bm25 query(필드/필터 축소) 보조 실행
- 효과: tail latency(p99) 감소 목표

### 5) Response / Debug annotation
- response.pipeline:
  - `degraded`: true/false
  - `degrade_reasons`: [..]
  - `stages`: { bm25: ok/timeout/fail, vector: ..., rerank: ... }

## Non-goals
- OpenTelemetry 전체 세팅(I-0302)
- RS 비용 가드레일(B-0253) (연동은 하되 여기선 SR 관점)

## DoD
- stage별 timeout 적용(기본값 + config)
- downstream 서킷브레이커 + bulkhead 적용
- degrade 정책 구현 + 결과에 표시
- chaos 시나리오 테스트:
  - MIS down, OS slow, RS timeout 등에서 “응답 반환 + 이유 기록” 확인

## Observability
- metrics:
  - sr_stage_timeout_total{stage}
  - sr_circuit_open_total{downstream}
  - sr_degraded_total{reason}
  - sr_partial_success_total
- logs:
  - request_id, degrade_reasons, stage_status, latency breakdown

## Codex Prompt
Make SR reliable:
- Add per-stage timeouts and total budget enforcement.
- Add circuit breakers + bulkheads for OS/MIS/RS.
- Implement degrade policies (bm25-only, fused-only) with reason codes.
- Annotate response.pipeline with stage status and degrade reasons.
- Add chaos tests/simulations for dependency failures.
