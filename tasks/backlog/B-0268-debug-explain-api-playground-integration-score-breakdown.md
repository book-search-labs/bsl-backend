# B-0268 — SR Debug/Explain API + Playground Snapshot (Score breakdown)

## Goal
Debug/Explain API**
Query→retrieval→fusion→rerank Before the process can be recorded/readed with “reactive form”.

- “Search Playground”
- Connect with A-0124(Ricing Debug/Replay UI)

## Background
- If Hybrid/LTR/Cross-encoder is mixed, it is impossible to improve.
- Debug must be provided only on internal/recommended basis without having to be in compliance with actual service response.

## Scope
### 1) Debug endpoint (internal)
- POST `/internal/search:explain`
  - request: regular search req +   TBD  
  - response:
    - final items
    - stage breakdown
    - retrieval candidates (topN), vector candidates (topK chunks), fused(topM), rerank(topR)
    - scores:
      - bm25_score
      - vec_score(best_chunk_score)
      - rrf_score (rank-based)
      - rerank_score (ltr/ce)
    - timings per stage

### 2) Snapshot persistence (optional but recommended)
- table: `playground_snapshot`
  - snapshot_id, request_id, created_by(admin_id), query_json, response_json(summary), created_at
- size guard:
  - store topN/topK/topR high end application
  - raw text(long snippet)

### 3) Access control
- Admin RBAC need(B-0227 link)
- Records in audit log

### 4) UX hooks
- response:
  - New  TBD   Return
- In Admin UI:
  - Open → replay/search:explain

## Non-goals
- Admin UI(A-0124) implementation itself
- RS debug payload(B-0252)

## DoD
- New  TBD  Implementation + Upgrading
- Stage candidate and score breakdown
- snapshot save/view (optional) or provide minimal replay payload
- User Guide

## Observability
- metrics:
  - sr_explain_requests_total
  - sr_snapshot_saved_total
  - sr_explain_payload_bytes
- logs:
  - request_id, admin_id, snapshot_id

## Codex Prompt
Add SR explain + snapshot:
- Implement /internal/search:explain returning stage candidates and score breakdown (bm25/vec/rrf/rerank) with timings.
- Add payload size guards and truncation.
- Optionally persist snapshots (playground_snapshot) for replay; include snapshot_id in response.
- Protect with Admin RBAC and record audit_log entries.
