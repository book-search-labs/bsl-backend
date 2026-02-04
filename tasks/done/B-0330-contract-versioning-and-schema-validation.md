# B-0235 — Contracts 정렬: BFF/SR/QS 요청·응답 스키마 버저닝 + 검증 게이트

## Goal
- 검색 파이프라인 핵심 계약을 버저닝 + CI 검증으로 올린다.
- 대상:
  - BFF `/v1/search`
  - SR `/search`
  - QS `/query/prepare`, `/query/enhance`

## Why
- “Contracts are versioned” 원칙 준수
- 문서/구현 drift 방지

## Scope
### In scope
- JSON Schema/OpenAPI로 계약 정의
  - qc.v1.1
  - bff_search_request/response
  - sr_search_request/response
  - enhance_request/response
- CI schema validation step 추가/확장

## Acceptance Criteria
- [ ] 계약 변경 시 CI에서 validation 수행
- [ ] schemaVersion/version 필드 일관

## Test plan
- 샘플 payload로 validate
