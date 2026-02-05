# File: tasks/backlog/B-0265-qsv1-2pass-spell-t5-implementation.md

# B-0265 — QS: Implement real 2-pass Spell (T5) for /query/enhance

## Goal
`POST /query/enhance`에서 SPELL 전략이 선택되었을 때 placeholder(no-op) 대신
실제 spell correction을 수행하여 q_spell이 의미 있게 개선될 수 있게 한다.

## Current State
- enhance gating/예산/쿨다운/캡/캐시/메트릭은 구현됨.
- 하지만 `_apply_spell`이 no-op로 동작(placeholder).
- T5 spell / LLM rewrite / RAG rewrite는 아직 실제로 동작하지 않음.

## Scope
- Spell 구현 옵션 중 1개를 선택하여 구현:
  A) QS 내부에서 T5 로드 (HF Transformers / ONNX Runtime)
  B) MIS에 /v1/spell (or /v1/text-correct) 추가 후 QS가 HTTP 호출  **(운영/격리 추천)**
- 최소 결과 스펙:
  - `spell: { q_spell, method, confidence }`
- Timeout/예산 준수:
  - latency budget 초과 시 즉시 degrade(원문 유지 + reason code)

## Non-goals
- LLM rewrite 구현은 별도 티켓(B-0266)
- spell 모델 고급 튜닝/데이터 학습은 범위 아님(초기 모델 서빙만)

## Interfaces
- Endpoint: `POST /query/enhance`
- Response changes:
  - `spell.q_spell` potentially different from input
  - `spell.confidence` filled
  - `decision/strategy/reason_codes`는 기존 유지

## DoD
- SPELL_ONLY 또는 SPELL_THEN_REWRITE에서 실제 spell correction 수행.
- confidence 낮거나 규칙 위반 시 원문 유지(보수적).
- metrics 추가:
  - `qs_spell_attempt_total`, `qs_spell_applied_total`, `qs_spell_rejected_total`
  - latency histogram/timer (가능하면)
- failures는 reason_codes + logs에 남김.
- tests:
  - deterministic unit tests (모델이 비결정적이면 mock/fixture로 대체)
  - 최소 5개 케이스: 오타, 붙여쓰기, 권차, 영문 혼용, 이상 입력

## Files to Change
- `services/query-service/app/core/enhance.py` (spell invoke hook)
- `services/query-service/app/api/routes.py` (spell response fill)
- (Option B일 때) `services/model-inference-service/...` (spell endpoint)
- `services/query-service/app/core/cache.py` (cache payload includes spell)
- tests

## Commands
- `cd services/query-service && pytest -q`
- (Option B) `cd services/model-inference-service && pytest -q` (있다면)

## Notes
- 초기엔 "모델 없는 환경"에서도 동작하도록:
  - provider=off/placeholder fallback 지원
  - CI에서는 mock으로 검증

## Codex Prompt
Implement a real spell correction path for QS /query/enhance (remove no-op).
Prefer calling MIS via HTTP if available; otherwise add a minimal local implementation with mocks in tests.
Add metrics and tests. Keep changes isolated.
