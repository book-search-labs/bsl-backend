# A-0124 — Admin Failure Case + Rerank Debug + Replay UI (Search/RAG)

## Goal
검색/리랭킹/RAG의 **실패 케이스를 수집·분석·재현**하는 운영 UI 제공.
- 0 results / low confidence / timeout / 이상치 등
- pipeline 단계별 score breakdown 확인
- 재실행(replay)로 재현 가능한 디버깅 루프 구축

## Background
- 운영 환경에서 품질 이슈는 “재현 가능성”이 핵심.
- RS/MIS/LTR 튜닝은 실패 케이스가 없으면 감으로 하게 된다.

## Scope
### 1) Failure Case List
- 타입:
  - SEARCH_ZERO_RESULTS
  - SEARCH_LOW_CONFIDENCE
  - RERANK_TIMEOUT / MIS_TIMEOUT
  - HYBRID_VECTOR_FAILURE
  - RAG_UNGROUNDED / MISSING_CITATION
- 표시 필드:
  - created_at, request_id, trace_id, session_id
  - query(q_raw/q_norm), filters, pipeline flags
  - error_code, latency breakdown(가능하면)

### 2) Failure Case Detail
- Request snapshot
  - query, filters, sort, page/size
  - pipeline config(bm25/hybrid/rrf/rerank model)
- Result snapshot
  - retrieval topN, fusion topM, rerank topK
  - stage별 점수/순위/이유 코드
- 로그 링크(선택): trace/span, raw json

### 3) Playground (Run)
- 운영자가 파라미터를 바꿔 재실행:
  - mode: bm25-only / hybrid
  - fusion: rrf / weighted (옵션)
  - rerank: off / ltr / cross-encoder (모델 버전 선택)
  - budgets: topN/topM/topK
- 결과 비교(diff):
  - before/after NDCG proxy(간이), top10 변화 표시

### 4) Replay
- request_id 기반 replay 실행
- replay 결과를 “새 playground_run”으로 저장

## Non-goals
- SR/RS 내부 디버그 구현 자체(B-0268/B-0252)
- 모델 학습 파이프라인(B-0294)

## Data / API (via BFF)
- `GET /admin/debug/failures?type=...&from=...&to=...`
- `GET /admin/debug/failures/{failure_id}`
- `POST /admin/debug/playground/run`
- `GET /admin/debug/playground/runs/{run_id}`
- `POST /admin/debug/replay?request_id=...`

## Persistence (suggested)
- failure_case(failure_id, type, request_id, trace_id, payload_json, created_at)
- playground_run(run_id, actor_admin_id, config_json, result_json, created_at)

## Security / Audit
- replay/run은 audit_log 기록(운영 위험)
- 모델 버전 선택은 RBAC 권한 필요(선택)

## DoD
- 실패 케이스를 request_id로 재현 가능
- 단계별 결과/점수 breakdown 확인 가능
- 설정 변경 후 재실행 비교까지 가능
- BFF 경유 + RBAC + audit_log

## Codex Prompt
Admin(React)에서 Failure Case/Playground/Replay UI를 구현하라.
실패 케이스 리스트/상세, pipeline 옵션을 바꿔 실행하는 playground, request_id replay를 제공하라.
결과는 stage별 breakdown으로 보여주고 BFF API만 사용하라.
