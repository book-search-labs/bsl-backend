# File: tasks/backlog/B-0264a-qsv1-prepare-canonical-key-bugfix.md

# B-0264a — QS: /query/prepare v1 canonical_key bugfix

## Goal
`POST /query/prepare` (v1) 응답에서 `canonical_key`가 undefined/누락되는 버그를 수정해,
Search 파이프라인에서 안정적으로 재사용 가능한 키를 항상 제공한다.

## Current State
- QS는 1-pass 정규화/분석 로직과 canonical_key 생성 로직이 존재한다.
- qc.v1.1 응답에는 debug/cache 정보 포함.
- 하지만 `/query/prepare` v1 응답 빌더에서 `canonical_key`를 참조하면서도 정의/할당이 누락된 상태로 보임(버그).

## Scope
- v1 응답 빌더에서 canonical_key 생성/전달 경로를 정리한다.
- canonical_key 생성 규칙은 analyzer 결과(이미 존재하는 계산)를 단일 소스로 사용한다.
- 응답 스키마/contract와 일치하도록 필드 위치/이름을 확정한다.

## Non-goals
- canonical_key 알고리즘/스펙 변경(규칙 변경)은 이번 티켓 범위 아님
- 2-pass enhance 동작 개선은 별도 티켓에서 수행

## Interfaces
- Endpoint: `POST /query/prepare`
- Response:
  - `canonical_key` MUST be present
  - (가능하면) `detected.mode`, `q_norm`, `q_nospace` 등 기존 필드 유지

## DoD
- `/query/prepare` 응답에 `canonical_key`가 항상 포함된다.
- 대표 입력 케이스(일반/초성/ISBN/권차/혼용)에서 `canonical_key` 존재 및 stable 확인.
- Unit test 추가:
  - `canonical_key` non-empty
  - 동일 입력에 대해 stable(결정적)하게 동일 키 생성
- Lint/Test 통과

## Files to Change
- `services/query-service/app/api/routes.py` (v1 response builder)
- (필요 시) `services/query-service/app/core/analyzer.py` (반환 구조 확인)
- (필요 시) `contracts/*` (스키마가 불일치할 경우만 최소 수정)
- `services/query-service/tests/...` (테스트 추가)

## Commands
- `cd services/query-service`
- `pytest -q`
- (optional) `ruff check .` / `mypy` (repo 설정에 따름)

## Notes
- canonical_key는 norm/mode/volume/isbn/series/locale 등을 조합한 hash로 이미 계산되는 것으로 설명됨.
- v1 응답에서도 동일한 canonical_key를 그대로 노출하는 것이 목적.

## Codex Prompt
Fix the v1 /query/prepare response so canonical_key is always defined and returned.
Add tests for canonical_key presence and stability across representative query modes.
Keep changes minimal.
