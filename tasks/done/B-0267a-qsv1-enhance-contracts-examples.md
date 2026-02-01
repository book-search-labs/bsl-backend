# File: tasks/backlog/B-0267a-qsv1-enhance-contracts-examples.md

# B-0267a — Contracts: QS prepare/qc/enhance schemas + examples (SSOT)

## Goal
BFF↔QS, SR↔QS 통신이 흔들리지 않도록 QS endpoints의 JSON Schema/OpenAPI를 SSOT로 고정하고
예시 파일을 최신 구현과 일치시킨다.

## Scope
- contracts:
  - prepare v1 request/response
  - qc v1.1 request/response
  - enhance request/response
- examples:
  - ZERO_RESULTS → spell_then_rewrite
  - HIGH_OOV → spell_only
  - LOW_CONFIDENCE → rewrite_only
  - USER_EXPLICIT → rag_rewrite

## Non-goals
- 전체 BFF/SR/AC 계약 확장(대형)은 B-0226에서 별도 수행
- 신규 기능 구현은 범위 아님(스키마/예시 정합만)

## DoD
- contracts와 실제 응답 필드가 일치
- jsonschema validation 스크립트/CI 통과
- breaking change 발생 시 명시적으로 버전업 또는 optional 처리

## Files to Change
- `contracts/*.schema.json`
- `contracts/examples/*.json`

## Commands
- repo의 schema 검증 커맨드(예: `./scripts/validate_schemas.sh` 등) 실행

## Codex Prompt
Update QS-related JSON schemas and examples to match current implementation plus new optional fields (spell/rewrite/rag hints).
Ensure schema validation passes in CI.
