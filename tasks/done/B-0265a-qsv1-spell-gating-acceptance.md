# File: tasks/backlog/B-0265a-qsv1-spell-gating-acceptance.md

# B-0265a — QS: Spell accept/reject guardrails

## Goal
Spell 결과가 과도하게 변형되거나 도메인 정보를 손상시키지 않도록
보수적인 accept/reject 규칙을 도입한다.

## Scope
- accept/reject rules (baseline):
  - length ratio clamp (e.g., 0.6~1.6)
  - edit distance threshold (relative)
  - ISBN/numeric token preservation (digits/hyphens)
  - volume token consistency (권/vol) 유지
  - forbidden chars / control chars reject
- reason_codes에 reject 사유 포함
- optional: spell_candidate만 제공하고 최종 채택은 SR에서 수행할 수 있도록 "candidate" 필드 분리

## Non-goals
- 품질 최적화를 위한 학습/튜닝은 범위 아님
- SR 전/후 비교 로직은 별도 티켓(B-0266a)

## Interfaces
- `/query/enhance` 응답:
  - `spell.applied: true/false` (optional)
  - `reason_codes`에 `spell_reject_*` codes 추가

## DoD
- spell 결과가 이상치인 경우 자동 reject + 원문 유지
- 테스트 케이스 20개 이상(텍스트 fixture 기반)
- 로그/메트릭에 reject count 노출

## Files to Change
- `services/query-service/app/core/enhance.py` or `core/spell.py` (new helper)
- tests

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Add conservative guardrails for spell results and comprehensive tests (20+).
Expose reject reason codes and keep behavior backward compatible.
