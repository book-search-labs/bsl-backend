# File: tasks/backlog/B-0268-qsv1-e2e-tests-prepare-enhance-cache-budgets.md

# B-0268 — QS: E2E tests for prepare/enhance, caching, budgets, degrade

## Goal
운영형 뼈대(캐시/예산/쿨다운/캡/게이팅)가 깨지면 즉시 감지할 수 있도록
QS에 E2E 테스트를 추가한다.

## Scope
- prepare:
  - cache miss → hit
  - canonical_key 존재
- enhance gating:
  - reason 없으면 SKIP
  - ISBN이면 SKIP
  - window budget 초과 시 SKIP + deny cache
  - cooldown hit 시 SKIP
  - per-query cap hit 시 SKIP
- degrade:
  - spell/rewrite provider timeout 시 200 + 원문 유지 + reason_codes
- metrics:
  - counters 증가 확인(가능하면)

## Non-goals
- 실제 LLM/T5 품질 평가는 범위 아님(동작/안정성만)
- 외부 서비스(OpenSearch/MIS) 통합테스트는 optional(기본은 mock)

## DoD
- 최소 10개 시나리오 E2E 테스트
- Redis 유무에 따라 통과(REDIS_URL 없으면 memory cache 경로로도 통과)
- CI에서 안정적으로 재현 가능

## Files to Change
- `services/query-service/tests/test_prepare.py`
- `services/query-service/tests/test_enhance_gating.py`
- `services/query-service/tests/test_caching_budgets.py`

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Add E2E tests for QS prepare/enhance covering caching, budgets (window/cooldown/caps), gating reasons, and degrade behavior.
Make tests pass with or without Redis by using configuration overrides.
