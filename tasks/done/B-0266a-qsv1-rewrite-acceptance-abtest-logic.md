# File: tasks/backlog/B-0266a-qsv1-rewrite-acceptance-abtest-logic.md

# B-0266a — QS↔SR: Provide rewrite candidate + acceptance hints (before/after compare)

## Goal
LLM rewrite를 무조건 적용하지 않고, Search Service가 전/후 비교로 최종 채택할 수 있도록
QS가 “후보+힌트”를 제공한다.

## Scope
- QS enhance 응답에:
  - `rewrite_candidate`(or rewrite.q_rewrite 그대로) + `confidence`
  - `acceptance_hints`:
    - `reason` (ZERO_RESULTS/LOW_CONFIDENCE/HIGH_OOV/USER_EXPLICIT)
    - `recommended_accept_if`: e.g. `results_improve`, `score_gap_improve`
- SR에 적용 가이드(문서 또는 contract 주석) 추가

## Non-goals
- SR 내부의 실제 전/후 비교 로직 구현은 SR 티켓에서 수행
- A/B 실험 프레임 전체 구축은 범위 아님

## Interfaces
- QS `/query/enhance` response additions:
  - `hints.acceptance` block (optional)
- SR `/internal/search` request:
  - (optional) QS hints 전달

## DoD
- QS 응답에 acceptance hints가 포함되고, 기존 필드와 충돌 없음
- contracts/examples 업데이트
- 테스트: hints 포함 여부 확인

## Files to Change
- `services/query-service/app/api/routes.py`
- `contracts/*`
- docs (optional)

## Commands
- schema validation + tests

## Codex Prompt
Add optional acceptance hints in QS enhance response so SR can do before/after comparison for rewrite adoption.
Update contracts and examples accordingly.
