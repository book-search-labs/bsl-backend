# A-0133 — Admin Search Compare UI (A/B/C)

## Goal
Admin에서 동일한 query를 여러 정책/전략(A/B/C)으로 실행하고 결과 차이를 비교할 수 있는 Compare UI를 제공한다.

## Background
- `/tools/compare` 페이지가 현재 Placeholder 상태.
- 실험/정책 변경 시 결과 차이를 빠르게 확인해야 함.

## Scope
- 입력 영역
  - query, size, vector on/off, debug on/off
  - 정책/전략 선택 (A/B/C)
- 결과 비교
  - 결과 리스트 나란히 표시
  - 교집합/순위 변동 요약 (overlap %, rank diff)
- 디버그 출력
  - 각 결과의 query_dsl, fallback 적용 여부 요약

## API (BFF)
> 신규 API 필요. 계약/스키마는 별도 PR에서 정의.
- `POST /admin/tools/compare`
  - payload: { query, options, variants: [ { policy_id, strategy_id, label } ] }

## DoD
- 2~3개 변형 결과를 동시에 비교 가능
- overlap/rank diff 요약이 제공됨
- 에러/로딩 상태 UX 제공

## Codex Prompt
Admin(React)에서 Compare UI를 구현하라.
A/B/C 변형으로 검색을 실행하고 결과 리스트를 나란히 보여주며, overlap 및 rank 변화 요약을 표시하라.
