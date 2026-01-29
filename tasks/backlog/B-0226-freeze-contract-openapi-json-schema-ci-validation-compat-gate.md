# B-0226 — Contract Freeze (OpenAPI/JSON Schema) + CI Compatibility Gate

## Goal
In the BFF-centric architecture, the contract between the service is “contract”**,
New *breaking change is made by CI blocking**.

- Target:**BFF ↔ (QS/SR/AC)** Internal call + BFF external API part (3 wires)
- Contract: OpenAPI(HTTP) + JSON Schema(Request/Request Payload)
- CI: When changing**backward-compatible** check whether → merge/block

## Background
- Multi-services are operated not “Contract Documents” but “Build Failure Conditions”.
- especially because the front is switched to QS direct-call → BFF,
The contract breaks down immediately.

## Scope (Sprint 1: minimal)
### 1) Contract target definition (line range)
- **External (BFF public)**
  - `GET /books/{id}`
  - `GET /autocomplete`
  - `POST /search`
- **Internal (BFF ↔ services)**
  - `POST /internal/query/prepare` (QS)
  - `POST /internal/search` (SR)
  - `GET /internal/autocomplete` (AC)
> Internal/outer contracts are separated and managed (transfers are recommended)

### 2) Repo structure (suggested)
- `contracts/openapi/bff-public.yaml`
- `contracts/openapi/bff-internal.yaml`
- `contracts/jsonschema/`
  - `SearchRequest.schema.json`
  - `SearchResponse.schema.json`
  - `AutocompleteResponse.schema.json`
  - `BookDetailResponse.schema.json`
  - `ErrorResponse.schema.json`
- New  TBD   (version policy, compatibility rules)

### 3) Versioning rules
- SemVer:
  - **MAJOR**: breaking change
  - **MINOR**: backward compatible extension
  - **PATCH**: docs/bugfix only
- Compatibility rules:
  - ✅ add optional field
  - ✅ add new endpoint
  - ❌ remove field/endpoint
  - ❌ change type/enum shrink
  - ❌ make optional -> required

### 4) CI Gate
- In PR:
  - baseline(main) contract vs PR contract diff
  - Failure
- Tools:
  - OpenAPI diff: `openapi-diff`, `oasdiff`
  - JSON Schema diff: `json-schema-diff` or custom checks

## Non-goals
- Complete gRPC/Protobuf switch (add)
- All services contracted all APIs at once (with a ticket)

## Acceptance / DoD
- The contract file exists in repo and kept up to date
- Change contract diff in CI automatically executed
- Breaking change PR
- MAJOR Bump procedure is documented if you need to change the contract

## Observability
- Tag:
  - Outputs that have been deemed to be broken
- (Optional)   TBD   Auto creation

## Codex Prompt
Create contract artifacts for BFF public + internal APIs (search/autocomplete/book detail + internal QS/SR/AC calls).
Add JSON Schemas for req/resp/error.
Implement CI compatibility gate that fails on breaking changes using OpenAPI/JSON schema diff tooling.
Document versioning rules in contracts/README.md.
