# B-0226 — Contract Freeze (OpenAPI/JSON Schema) + CI Compatibility Gate

## Goal
BFF 중심 아키텍처에서 **서비스 간 계약(Contract)을 “고정”**하고,
**breaking change를 CI에서 차단**하는 운영 표준을 만든다.

- 대상: **BFF ↔ (QS/SR/AC)** 내부 호출 + BFF 외부 API 일부(우선 3개)
- 계약물: OpenAPI(HTTP) + JSON Schema(요청/응답 페이로드)
- CI: 변경 시 **backward-compatible** 여부 검사 → 실패하면 merge/block

## Background
- 멀티서비스는 “계약이 문서”가 아니라 “빌드 실패 조건”이어야 운영이 된다.
- 특히 프론트가 QS direct-call → BFF로 전환 중이므로,
  계약 깨짐은 즉시 장애로 이어짐.

## Scope (Sprint 1: minimal)
### 1) Contract 대상 정의(우선 범위)
- **External (BFF public)**
  - `GET /books/{id}`
  - `GET /autocomplete`
  - `POST /search`
- **Internal (BFF ↔ services)**
  - `POST /internal/query/prepare` (QS)
  - `POST /internal/search` (SR)
  - `GET /internal/autocomplete` (AC)
> 내부/외부 계약은 분리해서 관리(폴더 분리 권장)

### 2) Repo structure (suggested)
- `contracts/openapi/bff-public.yaml`
- `contracts/openapi/bff-internal.yaml`
- `contracts/jsonschema/`
  - `SearchRequest.schema.json`
  - `SearchResponse.schema.json`
  - `AutocompleteResponse.schema.json`
  - `BookDetailResponse.schema.json`
  - `ErrorResponse.schema.json`
- `contracts/README.md` (버전 정책, 호환성 규칙)

### 3) Versioning rules
- SemVer:
  - **MAJOR**: breaking change
  - **MINOR**: backward compatible extension
  - **PATCH**: docs/bugfix only
- Compatibility rules(예시):
  - ✅ add optional field
  - ✅ add new endpoint
  - ❌ remove field/endpoint
  - ❌ change type/enum shrink
  - ❌ make optional -> required

### 4) CI Gate
- PR에서:
  - baseline(main) 계약 vs PR 계약 diff
  - breaking이면 fail
- 도구(선택):
  - OpenAPI diff: `openapi-diff`, `oasdiff`
  - JSON Schema diff: `json-schema-diff` or custom checks

## Non-goals
- 완전한 gRPC/Protobuf 전환(추후)
- 모든 서비스 모든 API를 한 번에 계약화(확장 티켓으로)

## Acceptance / DoD
- 계약 파일이 repo에 존재하고 최신 상태로 유지됨
- CI에서 계약 변경 diff가 자동 실행됨
- breaking change PR은 CI fail
- 계약 변경이 필요하면 MAJOR bump 절차가 문서화됨

## Observability
- CI 로그에:
  - 어떤 규칙으로 breaking 판단했는지 출력
- (선택) `contracts/changelog.md` 자동 생성

## Codex Prompt
Create contract artifacts for BFF public + internal APIs (search/autocomplete/book detail + internal QS/SR/AC calls).
Add JSON Schemas for req/resp/error.
Implement CI compatibility gate that fails on breaking changes using OpenAPI/JSON schema diff tooling.
Document versioning rules in contracts/README.md.
