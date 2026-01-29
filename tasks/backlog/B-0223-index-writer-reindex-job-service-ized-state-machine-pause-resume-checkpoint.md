# B-0223 — Index Writer Service (reindex_job state machine, pause/resume)

## Goal
OpenSearch Reindex is serviced as “operable Job”.
- alias swap
- Based on the status mercinity**Provision of medium-sized/release/release**
- Provides API interlockable with Admin Ops UI(A-0113)

## Background
- High-capacity indexing is always experiencing failure/medium/release.
- Unable to run a single script → job system required

## Scope
### 1) Reindex Job Status
- states:
  - CREATED → PREPARE → BUILD_INDEX → BULK_LOAD → VERIFY → ALIAS_SWAP → CLEANUP → SUCCESS
  - FAILED(with retryable flag)
  - Operating Suspension: PAUSED
- transitions:
  - retry, cancel(optional)

### 2) Storage (DB)
- reindex_job(job_id, job_type, status, params_json, progress_json, error_json, created_at, updated_at)
- search_index_version(version_id, index_name, alias_name, status)
- search_index_alias(alias_name, active_index, updated_at)

### 3) API (internal via BFF)
- `POST /internal/index/reindex-jobs` (create)
- `GET /internal/index/reindex-jobs/{id}`
- `POST /internal/index/reindex-jobs/{id}/pause`
- `POST /internal/index/reindex-jobs/{id}/resume`
- `POST /internal/index/reindex-jobs/{id}/retry`

### 4) Verification (minimum)
- doc count threshold
- Sample query smoke tests(optional)
- mapping/version check

## Non-goals
- Multi Cluster Recolor
- rollup/rollover automation

## Observability
- job metrics:
  - reindex_job_duration
  - reindex_docs_per_sec
  - reindex_failures
- structured logs by job_id

## DoD
- Re-color job creation → Complete status can be left to DB and tracked
- pause/resume actually works (reopen after the middle)
- alias swap is atomized, and the rollback path is documented
- Ops UI can display progress by polling

## Codex Prompt
Build an Index Writer service with DB-backed reindex_job state machine.
Support create/pause/resume/retry, checkpoint progress, verify counts, and alias swap.
Expose internal APIs for BFF/Ops UI integration with metrics/logs.
