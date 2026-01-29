# B-0223a — Reindex Safety Guards (throttle/backoff/retry/partial failure)

## Goal
B-0223 Index Writer adds “safety device” to increase operational stability.
- Throttleing (Crusher Protection)
- Back-off/Resistant (Resistant Disorder)
- Part Failure Treatment (cross/reprocessing during specific batch failure)
- Safe interruption/refund (checkpoint)

## Scope
### 1) Throttling
- Bulk size, concurrency, refresh interval policy
- Automatic slowdown when cluster health(RED/YELLOW)

### 2) Backoff/Retry Policy
- transient errors(429/503/timeout) index backoff
- max retries + DLQ option

### 3) Partial failure handling
- Only items failed in bulk responses stored in a separate queue
- Resume batch reconstruction
- Failure to change job FAILED

### 4) Checkpoint
- cursor:
  - last_material_id / last_offset
- job resume checkpoint

## Non-goals
- right-once indexing
- index-level transactional semantics

## Data
- reindex job.progress json:
  - cursor, total, processed, failed, retries
- reindex error(job id, entity id, reason, payload hash, created at) (optional)

## DoD
- OpenSearch 429/timeout situation job automatically relax + resume
- When some of the bulk fails, “full interruption” is not treated as a ashdo/no fail policy
- Minimized duplicate indexing in pause/resume (Based on the left light key/Document id)

## Codex Prompt
Enhance reindex job safety:
implement throttling based on cluster health, retry/backoff for transient errors,
partial failure tracking + retry queue, and checkpointed resume semantics.
