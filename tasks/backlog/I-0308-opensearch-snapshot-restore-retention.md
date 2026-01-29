# I-0308 — OpenSearch Snapshot/Return + Retention (Index DR)

## Goal
For the OpenSearch index, the corrective snapshot + repair procedure + archive (retention)** is set to the operating standard.

## Why
- The index is possible to re-index, which requires “fast recovery” for disability/disability/delete
- alias/blue-green, and RTO (recovery time) with snapshots

## Scope
### Snapshot Repository
- filesystem repository (container volume mount)
- S3 repository

### Snapshot
- Snapshot Target:
  - `books_doc_*`, `books_vec_*`, `ac_candidates_*`, (RAG) `docs_*`
- Snapshot Cycle:
  - daily (or 6h) + manual snapshot before release
- include global state: false

### 3) Retention
- daily: 7-14
- weekly: 4 recently(optional)
- Automated Deletion Policy (Script/Cron)

### 4) Recovery Procedure (Runbook)
- restore to new cluster/new nodes
- alias reconnection
- + Smoke test

### 5) Verification/Monitoring
- Snapshot success rate/time
- Rehearsal 1 time or more

## Non-goals
- Multi-reproduction reproduction (out of the initial range)
- Fully Automatic failover(After)

## DoD
- Create snapshot repo and snapshot/delete script presence
-  TBD  
- Min. 1 Rehearsal (Local/Stage)
- alias based search spoke test passed

## Codex Prompt
Implement OpenSearch snapshot & restore:
- Create snapshot repository (filesystem for local/stage).
- Add scripts to create snapshots, list, delete old snapshots (retention).
- Write a runbook for restore and alias re-attach.
- Validate by snapshotting and restoring into a fresh OpenSearch instance.
