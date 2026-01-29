# A-0113 — Ops: Reindex / Job Run UI (job_run/reindex_job/ops_task)

## Goal
Operator **Recolored/Batchwork**A minimum Ops UI that can run/monitoring/relay.

## Scope
### 1) Job Runs
- job_run list/detail
  - status, started_at, finished_at, error_message
  - params_json pretty view
- actions:
  - retry
  - cancel(optional)

### 2) Reindex Jobs
- reindex_job list/detail
  - source index/version → target index/version
  - progress(%) / counts / checkpoint
  - alias swap status
- actions:
  - start reindex
  - pause/resume
  - rollback / abort(optional)

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
- “Current progress/last action” can be viewed at a glance
- Performing a redemption → Check the progress → Revisit the status of the shield
- All Risk Actions Audit log Records

## Codex Prompt
Implement Ops UI in Admin.
Create a JobRuns/ReindexJobs/OpsTasks tab and provide a list/retry/pause/resume.
