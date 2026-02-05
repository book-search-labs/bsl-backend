# B-0223 — Index Writer Service (reindex_job state machine, pause/resume)

## Goal
OpenSearch 재색인(reindex)을 “운영 가능한 Job”으로 서비스화한다.
- blue/green index 생성 → bulk index → 검증 → alias swap
- 상태머신 기반으로 **중단/재개/재시도/진행률** 제공
- Admin Ops UI(A-0113)와 연동 가능한 API 제공

## Background
- 대용량 인덱싱은 항상 실패/중단/재시작을 겪는다.
- 단발 스크립트는 운영 불가능 → job 시스템 필요

## Scope
### 1) Reindex Job 상태머신
- states:
  - CREATED → PREPARE → BUILD_INDEX → BULK_LOAD → VERIFY → ALIAS_SWAP → CLEANUP → SUCCESS
  - 실패: FAILED (with retryable flag)
  - 운영 중단: PAUSED
- transitions:
  - retry, resume, cancel(선택)

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
- sample query smoke tests(옵션)
- mapping/version 확인

## Non-goals
- 멀티 클러스터 재색인
- rollup/rollover 자동화(추후)

## Observability
- job metrics:
  - reindex_job_duration
  - reindex_docs_per_sec
  - reindex_failures
- structured logs by job_id

## DoD
- 재색인 job 생성 → 완료까지 상태가 DB에 남고 추적 가능
- pause/resume가 실제로 동작(중단 후 재개)
- alias swap이 원자적으로 수행되고, 롤백 경로가 문서화됨
- Ops UI가 polling해서 진행률을 표시 가능

## Codex Prompt
Build an Index Writer service with DB-backed reindex_job state machine.
Support create/pause/resume/retry, checkpoint progress, verify counts, and alias swap.
Expose internal APIs for BFF/Ops UI integration with metrics/logs.
