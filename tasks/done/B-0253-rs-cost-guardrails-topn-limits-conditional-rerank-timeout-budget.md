# B-0253 — Ranking Cost Guardrails (TopN/TopK budgets + Conditional Rerank)

## Goal
Ranking/리랭킹 비용을 운영형으로 제어한다.

- 후보 수(topN), 리랭크 대상(topR), 반환(topK) 예산 고정
- expensive 단계(cross-encoder 등)는 **조건부**로만 실행
- 타임아웃 예산 + degrade/fallback 기본 탑재
- “쿼리별/정책별”로 비용 제어 가능(향후 A/B/FeatureFlag 연계)

## Background
- 리랭킹은 “품질”과 동시에 “비용/지연”을 폭발시킨다.
- guardrail이 없으면 트래픽이 늘 때 p99이 무너지고, 모델 비용이 통제 불가.

## Scope
### 1) Budget config (env + policy)
- defaults:
  - `retrieval_topN` (SR에서 확보하지만 RS도 검증)
  - `rerank_topR` (예: 50)
  - `return_topK` (예: 20)
  - `feature_fetch_timeout_ms` (예: 25)
  - `infer_timeout_ms` (예: 120)
  - `total_timeout_ms` (예: 180)
- policy overrides:
  - intent/segment에 따라 rerank 생략 가능

### 2) Conditional rerank rules (v1)
- rerank 실행 조건 예:
  - `candidates_count >= min_candidates`
  - `query_context.need_rerank >= threshold`
  - `not low_latency_mode`
  - `not repeated_query_with_cache_hit` (옵션)
- rerank 생략 시:
  - LTR-only 또는 BM25+feature heuristic로 반환

### 3) Degrade strategy
- feature fetch timeout → default features로 계속 진행
- MIS infer timeout/fail → LTR-only(또는 fused order)로 반환
- 전체 timeout 초과 → 즉시 best-effort 결과 반환 + reason_code

### 4) Safety
- candidate 텍스트 길이/필드 제한(모델 입력 크기 폭발 방지)
- request payload validation + max size 제한

## Non-goals
- SR의 retrieval budget 정책(B-0266/0267) 구현 자체
- global governor(B-0306) (서비스 공통 예산제)

## DoD
- budget 파라미터가 config로 관리되고 runtime에서 강제
- rerank가 조건부로 실행되며, 생략/timeout 시 degrade 결과 반환
- debug(B-0252)에 reason_code로 기록
- 부하테스트에서 p99 예산 내 동작 확인

## Observability
- metrics:
  - rerank_invocations_total{strategy}
  - rerank_skipped_total{reason}
  - rerank_timeout_total
  - rs_degrade_total{reason}
- logs:
  - request_id, topN/topR/topK, strategy, degrade_reason

## Codex Prompt
Add cost guardrails to RS:
- Enforce topN/topR/topK and strict timeouts.
- Implement conditional rerank gating based on query_context + policy.
- Implement degrade paths on feature fetch and MIS inference failures.
- Emit metrics for skipped/timeout/degrade and integrate with debug output.
