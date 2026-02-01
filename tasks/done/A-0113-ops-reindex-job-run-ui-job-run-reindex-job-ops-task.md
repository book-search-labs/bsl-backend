# A-0113 — Ops: Reindex / Job Run UI (job_run/reindex_job/ops_task)

## Goal
운영자가 **재색인/배치 작업**을 실행/모니터링/재시도 할 수 있는 최소 Ops UI.

## Scope
### 1) Job Runs
- job_run list/detail
  - status, started_at, finished_at, error_message
  - params_json pretty view
- actions:
  - retry(권한 필요)
  - cancel(선택)

### 2) Reindex Jobs
- reindex_job list/detail
  - source index/version → target index/version
  - progress(%) / counts / checkpoint
  - alias swap 상태
- actions:
  - start reindex
  - pause/resume
  - rollback / abort(선택)

### 3) Ops Tasks
- ops_task list/detail
  - task_type, status, payload_json, assignee
- actions:
  - assign, change status, comment

## API (BFF)
- `GET /admin/ops/job-runs`
- `GET /admin/ops/reindex-jobs`
- `POST /admin/ops/reindex-jobs/start`
- `POST /admin/ops/job-runs/{id}/retry`
- `GET /admin/ops/tasks`

## DoD
- “현재 진행중/최신 작업”을 한 눈에 볼 수 있음
- 재색인 실행→진행률 확인→실패 시 재시도까지 가능
- 모든 위험 액션은 audit_log 기록

## Codex Prompt
Admin에서 Ops UI를 구현하라.
JobRuns/ReindexJobs/OpsTasks 탭을 만들고, 리스트/상세/핵심 액션(start/retry/pause/resume)을 제공하라.
