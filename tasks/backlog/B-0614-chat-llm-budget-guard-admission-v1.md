# B-0614 — Chat LLM Budget Guard v1 (Call/Token/Admission)

## Priority
- P0

## Dependencies
- B-0603
- B-0608

## Goal
대화 턴 증가에 따른 LLM 비용 폭주를 방지하고 서비스 헬스 기반으로 heavy path를 제어한다.

## Why
- 인터랙션 경로는 LLM 호출 수가 누적되어 비용/지연 리스크가 급증함

## Scope
### 1) Turn-level limits
- `max_llm_calls_per_turn`
- `max_prompt_tokens_per_turn`
- `max_completion_tokens_per_turn`

### 2) Admission control
- 예산 초과/헬스 저하 시 heavy path 차단
- degrade route(간소 응답/검색 only) 적용

### 3) Cost telemetry
- 모델/경로별 token burn, call rate, cache hit 추적

## DoD
- 상한 초과 시 fail-open 없이 제한이 적용된다.
- admission 정책이 p95/p99 악화 구간에서 동작한다.
- 비용 지표가 운영 대시보드에서 확인 가능하다.

## Interfaces
- llm gateway policy
- budget governor config

## Observability
- `chat_llm_calls_total{model,path}`
- `chat_llm_tokens_total{type,path}`
- `chat_admission_block_total{reason}`

## Test / Validation
- per-turn limit tests
- admission degrade tests
- budget alert pipeline tests

## Codex Prompt
Introduce LLM budget guardrails:
- Enforce per-turn call/token ceilings.
- Add health/budget based admission control for heavy paths.
- Publish cost and admission metrics for operations.
