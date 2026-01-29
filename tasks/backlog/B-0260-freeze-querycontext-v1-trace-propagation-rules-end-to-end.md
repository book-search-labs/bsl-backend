# B-0260 — QueryContext v1 Contract + Trace Propagation (E2E)

## Goal
Set the queryContext v1** to the contract (Contract),
BFF→QS→SR→RS/MIS In the previous section, **request id/trace id** will be consistent.

- QueryContext “Search Pipeline Shared Input Format”
- trace propagation prerequisites for “observation/debug/performance improvement”

## Background
- If QueryContext is shaken, SR/RS implementation is still broken and experimental.
- If you don't have trace id, you'll find that you don't have "lower / why degrade."

## Scope
### 1) QueryContext v1 schema (minimal but sufficient)
Tag:
- `request_id`, `trace_id`, `span_id?`
- `q_raw`, `q_nfkc`, `q_norm`, `q_nospace`
- `locale`, `client` (web/admin/mobile)
- `detected`:
  - `mode`: normal | chosung | isbn | mixed
  - `is_isbn`, `has_volume`, `lang`
- `hints`:
  - New  TBD   (Search/Item/Seller/Series)
  - New  TBD   (low latency mode)
- `confidence`:
  - `need_spell`, `need_rewrite`, `need_rerank` (0..1)
- `expanded` (optional):
  - aliases/series/author_variants

### 2) Contract storage
- `contracts/query_context/v1/*.json` (JSON Schema)
- OpenAPI includes QS endpoint request/response

### 3) Trace propagation rules
- incoming:
  - BFF   TBD  ,   TBD   creation/delivery
- QS:
  - Used traces received by header as true + included in the log
  - Internal call(Cache/Model) also generate span
- QS response:
  - echo request id/trace id in QueryContext
- SR/RS/MIS:
  - Follow Us

### 4) CI checks
- Contract breaking change detection (B-0226 link)
- schema validation test with sample payload fixtures

## Non-goals
- QS internal normalize/detect algorithm(B-0261)
- OTel Infrastructure (I-0302)

## DoD
- QueryContext v1 JSON Schema Fix + Fixed on repo
- QS   TBD   compliance v1
- request id/trace id from logs to BFF→QS→SR
- contract testing determines passing / shielding from CI

## Observability
- QS metrics:
  - qs_prepare_latency_ms
  - qs_schema_validation_fail_total
- logs:
  - request_id, trace_id, q_hash, detected.mode

## Codex Prompt
Define QueryContext v1:
- Add JSON Schema + fixtures and integrate into OpenAPI.
- Update QS prepare endpoint to output QueryContext v1.
- Implement trace propagation via x-request-id + traceparent and ensure logs include them.
- Add CI test that validates fixtures and rejects breaking changes.
