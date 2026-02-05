# B-0268 — SR Debug/Explain API + Playground Snapshot (Score breakdown)

## Goal
Search Service에 **Debug/Explain API**를 제공해서,
쿼리→retrieval→fusion→rerank 전 과정을 “재현 가능한 형태”로 기록/조회할 수 있게 한다.

- 개발/운영이 가능한 “검색 플레이그라운드” 기반
- A-0124(리랭킹 디버그/리플레이 UI)와 연결

## Background
- Hybrid/LTR/Cross-encoder가 섞이면 “왜 이 결과가 나왔는지” 모르면 개선 불가.
- Debug는 실서비스 응답에 무조건 넣지 않고, 내부/권한 기반으로만 제공해야 한다.

## Scope
### 1) Debug endpoint (internal)
- POST `/internal/search:explain`
  - request: 일반 search req + `debug=true`
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
  - store topN/topK/topR 상한 적용
  - raw text(긴 snippet)는 별도 truncate

### 3) Access control
- Admin RBAC 필요(B-0227 연계)
- audit_log에 기록

### 4) UX hooks
- response에:
  - `snapshot_id` 반환
- Admin UI에서:
  - snapshot list → open → replay/search:explain 실행

## Non-goals
- Admin UI(A-0124) 구현 자체
- RS debug payload(B-0252) 구현 자체 (연동만)

## DoD
- `/internal/search:explain` 구현 + 상한 적용
- stage별 후보와 score breakdown 제공
- snapshot 저장/조회(옵션) 또는 최소한 replay payload 제공
- 권한/감사로그 연결

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
