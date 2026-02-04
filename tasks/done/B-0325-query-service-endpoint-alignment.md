# B-0230 — Query Service Endpoint 정렬: /query/prepare 표준화 + /query-context Deprecate

## Goal
- **/query/prepare**를 “표준 QueryContext 생성 API”로 확정한다.
- 기존 **/query-context**는 **호환을 위해 alias**로 남기되, 문서/코드에서 **deprecated**로 표시한다.
- 응답 스키마는 **qc.v1.1**(현재 /query-context가 생성하는 형태)로 통일한다.

## Why
- Architecture v3: **BFF → QS /query/prepare → SR**
- 현재는 BFF가 /query-context에 의존 → SSOT와 불일치

## Scope
### In scope
- QS 라우터에서 `/query/prepare`가 qc.v1.1을 반환하도록 변경(또는 /query-context 로직 재사용)
- `/query-context`는 deprecated 주석 + 내부적으로 동일 구현 공유
- meta.schemaVersion 일관 유지(예: `qc.v1.1`)

### Out of scope
- LLM 기반 의미 이해
- SR의 품질 판정/재시도

## Deliverables
- `services/query-service/app/api/routes.py` 변경
  - `/query/prepare` → `_build_qc_v11_response(...)` 사용
  - `/query-context` → alias/deprecated
- `docs/API_SURFACE.md` 업데이트(prepare=primary, query-context=deprecated)

## Acceptance Criteria
- [ ] `POST /query/prepare`의 `meta.schemaVersion == "qc.v1.1"`
- [ ] `/query-context`와 `/query/prepare`가 동일 입력에 대해 동일 shape 반환
- [ ] 기존 호출자 호환 유지

## Test plan
- prepare vs query-context 응답 diff 비교 테스트
- 로컬 curl smoke
