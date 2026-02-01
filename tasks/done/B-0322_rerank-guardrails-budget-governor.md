# B-0322 — Rerank: guardrails + budget governor (topN/topR/timeout/cost)

## Goal
Rerank 호출이 “항상/무제한”이 되면 지연/비용/장애 전파가 커진다.
Search Service → Ranking Service → MIS 전 구간에 **예산(budget) 기반 가드레일**을 추가한다.

## Why
- p99 안정화(서빙 핵심)
- MIS 장애/과부하 시 검색 degrade를 자동화
- LTR/크로스인코더 결합 시 비용 폭주 방지

## Scope
### In-scope
1) Guardrail rules
- rerank_topR 기본값 및 상한
- query 조건(짧은 query, 특정 패턴, low intent 등)에서 rerank skip
- vector/lex 후보 품질 낮을 때 rerank skip
- fallback reason codes 표준화

2) Timeout budget propagation
- Search Service가 전체 budget을 가지고 stage별 timeout을 나눔
- Ranking Service/MIS 호출 타임아웃 통일

3) Rate/overload handling
- MIS 429/503 시 즉시 degrade
- exponential backoff 금지(서빙 요청에서 재시도는 최소)

### Out-of-scope
- 전역(검색+챗) 통합 governor(Phase 10-B-0306)

## DoD
- rerank가 “조건부”로만 실행되는 정책이 코드/설정으로 명확해짐
- MIS 다운 상황에서도 검색이 빠르게 degrade로 응답
- debug에서 rerank_used=false + reason 확인 가능

## Files (expected)
- `services/search-service/.../HybridSearchService.java`
- `services/ranking-service/.../RerankService.java`
- `services/ranking-service/.../MisClient.java`
- config yml

## Codex Prompt
- Implement rerank guardrails and budget governor across search-service and ranking-service.
- Add reason codes, config knobs, and ensure degrade behavior is correct.
