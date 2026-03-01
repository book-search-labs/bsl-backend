# API Surface (Service Endpoint Catalog)

This document defines the **public API surface** of the Book Search project.
It is intentionally concise, implementation-agnostic, and **must not contradict SSOT**.

---

## SSOT Order (Source of Truth)

1. `contracts/` — inter-service and public payload schemas + examples (**highest priority**)
2. `data-model/` + `db/` — catalog/source data model and persistence
3. `infra/opensearch/` — derived search index mappings/analyzers
4. `docs/` — rationale/runbooks (must not conflict with SSOT)

---

## Global Conventions

### Base URLs (Local Dev Defaults)

- BFF (Search API): `http://localhost:8088`
- Query Service (QS): `http://localhost:8001`
- Search Service (SS): `http://localhost:8002`
- Autocomplete Service (ACS): `http://localhost:8003`
- Ranking Service (RS): `http://localhost:8082`
- Model Inference Service (MIS): `http://localhost:8005`

> Ports are defaults for local development. Production deployment may differ.

### Common Headers

- `x-trace-id` (optional): if present, services should propagate it downstream
- `x-request-id` (optional): if present, services should propagate it downstream
- If not provided, services generate them and include them in structured responses where applicable.

### Common Fields (Structured Responses)

All structured responses that follow `contracts/*` must include:

- `version`
- `trace_id`
- `request_id`

### Error Responses

- MVP: services may return a minimal error shape:
  ```json
  { "error": { "code": "string", "message": "string" }, "trace_id": "string", "request_id": "string" }
  ```
- If `contracts/error.schema.json` exists, services **must** return that shape.

### Content Types

- Requests: `Content-Type: application/json`
- Responses: `application/json; charset=utf-8`

### Status Codes (MVP)

- `200 OK` — success
- `400 Bad Request` — invalid input
- `404 Not Found` — unknown route
- `500 Internal Server Error` — unexpected error (avoid leaking internals)

---

# 1) BFF (Search API)

**Responsibility**: single client entrypoint for search + autocomplete + book detail.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok", "trace_id": "string", "request_id": "string" }
```

## GET `/ready`
**Purpose**: readiness probe (downstream connectivity)  
**Response**: `200 OK`
```json
{
  "status": "ok|degraded",
  "trace_id": "string",
  "request_id": "string",
  "downstream": {
    "query_service": "ok|error",
    "search_service": "ok|error",
    "autocomplete_service": "ok|error"
  }
}
```

## POST `/auth/login`
**Purpose**: user login and Redis-backed session issue.
**Alias**: `POST /v1/auth/login`

### Request
- Contract: `contracts/auth-login-request.schema.json`
- Example: `contracts/examples/auth-login-request.sample.json`

### Response
- Contract: `contracts/auth-session-response.schema.json`
- Example: `contracts/examples/auth-session-response.sample.json`

### Notes
- On success, returns `session.session_id` and user profile.
- `session.session_id` must be forwarded via `x-session-id` header in subsequent requests.

## GET `/auth/session`
**Purpose**: get current authenticated session user.
**Alias**: `GET /v1/auth/session`

### Response
- Contract: `contracts/auth-session-response.schema.json`
- Example: `contracts/examples/auth-session-response.sample.json`

### Notes
- Returns `401` when session is missing or expired.

## POST `/auth/logout`
**Purpose**: invalidate current session.
**Alias**: `POST /v1/auth/logout`

### Request
- no body required
- client must send `x-session-id` header

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## POST `/search`
**Purpose**: fan-out to QS → SS and return SearchResponse (v1).
**Alias**: `POST /v1/search`

### Request
- Contract: `contracts/search-request.schema.json`
- Example: `contracts/examples/search-request.sample.json`

### Response
- Contract: `contracts/search-response.schema.json`
- Example: `contracts/examples/search-response.sample.json`

### Notes (MVP)
- If `query_context` is missing, BFF will derive it via QS using `query.raw` when present.
- Response includes `imp_id` + `query_hash` for search event logging.

## POST `/search/click`
**Purpose**: record a search result click event.
**Alias**: `POST /v1/search/click`

### Request
- Contract: `contracts/search-click-request.schema.json`
- Example: `contracts/examples/search-click-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## POST `/search/dwell`
**Purpose**: record a search result dwell event.
**Alias**: `POST /v1/search/dwell`

### Request
- Contract: `contracts/search-dwell-request.schema.json`
- Example: `contracts/examples/search-dwell-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## POST `/chat`
**Purpose**: RAG chat response with citations (BFF → QS `/chat`).  
**Alias**: `POST /v1/chat`

### Request
- Contract: `contracts/chat-request.schema.json`
- Example: `contracts/examples/chat-request.sample.json`

### Request Guardrails (runtime)
- `message.content` 최대 길이: `QS_CHAT_MAX_MESSAGE_CHARS` (기본 1200)
- `history` 최대 턴 수: `QS_CHAT_MAX_HISTORY_TURNS` (기본 12)
- `message + history` 총 길이: `QS_CHAT_MAX_TOTAL_CHARS` (기본 6000)
- `session_id` 형식: `QS_CHAT_SESSION_ID_PATTERN` / 길이 `QS_CHAT_SESSION_ID_MAX_LEN` 검증
- 인증된 사용자 요청은 `session_id`가 사용자 네임스페이스(`u:{user_id}:...`)로 정규화된다. 교차 사용자 세션(`u:{other_user}:...`)은 `403 forbidden`.
- `QS_CHAT_SEMANTIC_CACHE_ENABLED=1`인 경우에도 semantic cache는 정책/정적 안내 lane(토픽 일치 + 유사도 임계치 충족)에서만 제한적으로 재사용되며, 조회/쓰기성 질의는 차단된다.
- `client.memory_opt_in`(또는 `client.episode_memory_opt_in`)이 전달되면 사용자 동의 기반 episode memory 사용 여부를 즉시 갱신한다.
- 제한 위반 시 HTTP 200 + `status=insufficient_evidence`와 `reason_code`(`CHAT_MESSAGE_TOO_LONG`, `CHAT_HISTORY_TOO_LONG`, `CHAT_PAYLOAD_TOO_LARGE` 등)로 복구 힌트를 반환

### Response
- Contract: `contracts/chat-response.schema.json`
- Example: `contracts/examples/chat-response.sample.json`

### Recovery Hints (optional)
- `reason_code`: 실패/제한 사유 코드
- `recoverable`: 재시도/수정으로 복구 가능한지 여부
- `next_action`: 권장 사용자 다음 행동 (`RETRY`, `REFINE_QUERY`, `LOGIN_REQUIRED`, `PROVIDE_REQUIRED_INFO`, `CONFIRM_ACTION`, `OPEN_SUPPORT_TICKET`, `NONE`)
- `retry_after_ms`: 재시도 권장 지연(ms), 없으면 `null`
- `fallback_count`: 현재 세션 fallback 누적 횟수
- `escalated`: 반복 실패로 상담 전환 권고 상태인지 여부

### Streaming (optional)
- `POST /chat?stream=true` returns `text/event-stream`
- Events:
  - `meta` (trace/request metadata)
  - `delta` (token chunk payload)
  - `error` (reason code/message when degraded)
  - `done` (final status + citations + optional recovery hints)

## GET `/chat/session/state`
**Purpose**: BFF proxy for chat session diagnostics snapshot.
**Alias**: `GET /v1/chat/session/state`

### Query
- `session_id` (required)
- 인증된 사용자 요청에서 `session_id`가 `u:{user_id}:...` 형식이 아니면 사용자 네임스페이스로 정규화된다. 다른 사용자 네임스페이스는 `403 forbidden`.

### Response
- Contract: `contracts/chat-session-state-response.schema.json`
- Example: `contracts/examples/chat-session-state-response.sample.json`
- Optional diagnostics: `session.state_version`, `session.last_turn_id`, `session.llm_call_budget` (`count/limit/limited/window_sec/window_start`), `session.selection_snapshot`, `session.pending_action_snapshot`, `session.semantic_cache` (`enabled/auto_disabled/disable_reason/drift_total/drift_errors/drift_error_rate`), `session.episode_memory` (`enabled/opt_in/count/items`), `session.recommend_experiment` (`enabled/auto_disabled/block_rate/total/blocked/diversity_percent/quality_min_candidates/config_overrides`)

## POST `/chat/session/reset`
**Purpose**: BFF proxy for chat session diagnostics reset.
**Alias**: `POST /v1/chat/session/reset`

### Request
```json
{
  "session_id": "u:101:default"
}
```
- 인증된 사용자 요청에서 `session_id`가 `u:{user_id}:...` 형식이 아니면 사용자 네임스페이스로 정규화된다. 다른 사용자 네임스페이스는 `403 forbidden`.

### Response
- Contract: `contracts/chat-session-reset-response.schema.json`
- Example: `contracts/examples/chat-session-reset-response.sample.json`
- Optional diagnostics: `session.state_version`, `session.previous_llm_call_count`, `session.previous_episode_memory_count`, `session.episode_memory_cleared`

## POST `/chat/feedback`
**Purpose**: user feedback for chat answers (👍/👎 + flags).  
**Alias**: `POST /v1/chat/feedback`

### Request
- Contract: `contracts/chat-feedback-request.schema.json`
- Example: `contracts/examples/chat-feedback-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`

### Notes
- `rating`은 `up|down`만 허용되며, 그 외 값은 `400 bad_request`.
- 인증된 사용자 요청은 `session_id`가 사용자 네임스페이스(`u:{user_id}:...`)로 정규화된다.
- 인증 상태에서 다른 사용자 네임스페이스(`u:{other_user}:...`)는 `403 forbidden`.
- 피드백 이벤트는 BFF outbox(`chat_feedback_v1`)로 기록되며 `actor_user_id`, `auth_mode`를 포함한다.

## GET `/chat/recommend/experiment`
**Purpose**: proxy recommendation experiment diagnostics from Query Service (ops/admin only).  
**Alias**: `GET /v1/chat/recommend/experiment`

### Response
- Contract: `contracts/chat-recommend-experiment-response.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-response.sample.json`

### Notes
- 관리자 인증 컨텍스트가 없으면 `403 forbidden`.
- 응답 본문은 Query Service `/internal/chat/recommend/experiment` payload를 그대로 전달한다.

## POST `/chat/recommend/experiment/reset`
**Purpose**: reset recommendation experiment runtime state (ops/admin only).  
**Alias**: `POST /v1/chat/recommend/experiment/reset`

### Request
- Contract: `contracts/chat-recommend-experiment-reset-request.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-reset-request.sample.json`

### Response
- Contract: `contracts/chat-recommend-experiment-reset-response.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-reset-response.sample.json`

### Notes
- 관리자 인증 컨텍스트가 없으면 `403 forbidden`.
- `overrides`는 선택 입력이며 runtime 실험 설정을 즉시 갱신한다.
- `clear_overrides=true`면 기존 override를 비우고 `overrides`만 다시 적용한다.
- 응답 본문은 Query Service `/internal/chat/recommend/experiment/reset` payload를 그대로 전달한다.

## POST `/chat/recommend/experiment/config`
**Purpose**: patch recommendation experiment runtime overrides without resetting counters (ops/admin only).  
**Alias**: `POST /v1/chat/recommend/experiment/config`

### Request
- Contract: `contracts/chat-recommend-experiment-config-update-request.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-config-update-request.sample.json`

### Response
- Contract: `contracts/chat-recommend-experiment-config-update-response.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-config-update-response.sample.json`

### Notes
- 관리자 인증 컨텍스트가 없으면 `403 forbidden`.
- `clear_overrides=true` 또는 `overrides` patch 중 하나는 필수다.
- 응답 본문은 Query Service `/internal/chat/recommend/experiment/config` payload를 그대로 전달한다.

## GET `/autocomplete`
**Purpose**: return query suggestions for a prefix.

### Request (Query Params)
- `q` (string, optional): prefix. empty value returns trending/recommended suggestions.
- `size` (int, optional, default=10)

### Response (Planned MVP Shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "took_ms": 1,
  "suggestions": [
    { "text": "string", "score": 0.0, "source": "redis|opensearch", "suggest_id": "string", "type": "string" }
  ]
}
```

## GET `/categories/kdc`
**Purpose**: return KDC category tree (depth 0-2).

### Response
- Contract: `contracts/kdc-category-response.schema.json`
- Example: `contracts/examples/kdc-category-response.sample.json`

## POST `/autocomplete/select`
**Purpose**: record a suggestion selection event.

### Request
- Contract: `contracts/autocomplete-select-request.schema.json`
- Example: `contracts/examples/autocomplete-select-request.sample.json`

### Response
- Contract: `contracts/ack-response.schema.json`
- Example: `contracts/examples/ack-response.sample.json`

## GET `/books/{docId}`
**Purpose**: book detail by doc id.
**Alias**: `GET /v1/books/{docId}`

### Response (MVP Shape)
```json
{
  "doc_id": "string",
  "source": {
    "title_ko": "string",
    "authors": ["string"],
    "isbn13": "string"
  },
  "trace_id": "string",
  "request_id": "string",
  "took_ms": 1
}
```

# 1.2) BFF Admin Ops (Internal/Admin)

**Responsibility**: operational visibility and control for reindex + batch jobs.

## GET `/admin/ops/job-runs`
**Purpose**: list recent job runs.  
**Query Params**: `limit` (int, optional), `status` (string, optional)  
**Response**: `contracts/job-run-list-response.schema.json`

## GET `/admin/ops/job-runs/{id}`
**Purpose**: get a single job run.  
**Response**: `contracts/job-run-response.schema.json`

## POST `/admin/ops/job-runs/{id}/retry`
**Purpose**: retry a failed job run (creates a new job_run row).  
**Response**: `contracts/job-run-response.schema.json`

## GET `/admin/ops/reindex-jobs`
**Purpose**: list reindex jobs.  
**Query Params**: `limit` (int, optional), `status` (string, optional), `logical_name` (string, optional)  
**Response**: `contracts/reindex-job-list-response.schema.json`

## POST `/admin/ops/reindex-jobs/start`
**Purpose**: start a new reindex job.  
**Request**: `contracts/reindex-job-create-request.schema.json`  
**Response**: `contracts/reindex-job-response.schema.json`

## BFF Admin Model Ops (Internal/Admin)

**Responsibility**: model registry visibility + rollout/canary + eval report access.

## GET `/admin/models/registry`
**Purpose**: list model registry state (proxy to MIS).  
**Response**: `contracts/mis-models-response.schema.json`

## POST `/admin/models/registry/activate`
**Purpose**: set an active model for a task (rollout/rollback).  
**Request (MVP)**:
```json
{ "model_id": "string", "task": "rerank" }
```
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/models/registry/canary`
**Purpose**: set canary model + weight.  
**Request (MVP)**:
```json
{ "model_id": "string", "task": "rerank", "canary_weight": 0.05 }
```
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/models/registry/rollback`
**Purpose**: rollback to a previous model (alias of activate).  
**Request/Response**: same as `/admin/models/registry/activate`

## GET `/admin/models/eval-runs`
**Purpose**: list offline eval reports (golden/shadow/hard).  
**Response (MVP shape)**:
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "count": 1,
  "items": [
    {
      "run_id": "string",
      "generated_at": "date-time",
      "sets": { "golden": { "ndcg_10": 0.0 } },
      "overall": { "ndcg_10": 0.0 }
    }
  ]
}
```

## BFF Admin RAG Ops (Internal/Admin)

**Responsibility**: document upload + index reindex/rollback + eval labeling.

## POST `/admin/rag/docs/upload`
**Purpose**: upload a RAG document (stored for later indexing).  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/index/reindex`
**Purpose**: create a RAG reindex ops task.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/index/rollback`
**Purpose**: create a RAG rollback ops task.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/rag/eval/label`
**Purpose**: store manual eval/label judgments for RAG answers.  
**Response**: `contracts/ack-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/pause`
**Purpose**: pause a running reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/resume`
**Purpose**: resume a paused reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/admin/ops/reindex-jobs/{id}/retry`
**Purpose**: retry a failed reindex job.  
**Response**: `contracts/reindex-job-response.schema.json`

## GET `/admin/ops/tasks`
**Purpose**: list ops tasks.  
**Query Params**: `limit` (int, optional), `status` (string, optional), `task_type` (string, optional)  
**Response**: `contracts/ops-task-list-response.schema.json`

## GET `/admin/ops/autocomplete/suggestions`
**Purpose**: search autocomplete suggestions for ops review.  
**Query Params**: `q` (string), `size` (int, optional), `include_blocked` (bool, optional)  
**Response**: `contracts/autocomplete-admin-suggestions-response.schema.json`

## POST `/admin/ops/autocomplete/suggestions/{id}`
**Purpose**: update suggestion weight/blocking.  
**Request**: `contracts/autocomplete-admin-update-request.schema.json`  
**Response**: `contracts/autocomplete-admin-update-response.schema.json`

## GET `/admin/ops/autocomplete/trends`
**Purpose**: top suggestions by CTR/Popularity.  
**Query Params**: `metric` (ctr|popularity|impressions, optional), `limit` (int, optional)  
**Response**: `contracts/autocomplete-admin-trends-response.schema.json`

## GET `/admin/ops/metrics/summary`
**Purpose**: return operational metric summary for the selected window.  
**Query Params**: `window` (`15m|1h|24h`, optional; default `15m`)  
**Response**: `contracts/admin-ops-metrics-summary-response.schema.json`  
**Example**: `contracts/examples/admin-ops-metrics-summary-response.sample.json`

## GET `/admin/ops/metrics/timeseries`
**Purpose**: return time-bucketed metric points for dashboard sparkline cards.  
**Query Params**:
- `metric` (`query_count|p95_ms|p99_ms|zero_result_rate|rerank_rate|error_rate`, optional; default `query_count`)
- `window` (`15m|1h|24h`, optional; default `15m`)
**Response**: `contracts/admin-ops-metrics-timeseries-response.schema.json`  
**Example**: `contracts/examples/admin-ops-metrics-timeseries-response.sample.json`

## GET `/admin/authority/merge-groups`
**Purpose**: list material merge groups (canonical selection queue).  
**Query Params**: `limit` (int, optional), `status` (string, optional)  
**Response**: `contracts/authority-merge-group-list-response.schema.json`

## POST `/admin/authority/merge-groups/{id}/resolve`
**Purpose**: mark a merge group as resolved by selecting a master material.  
**Request**: `contracts/authority-merge-group-resolve-request.schema.json`  
**Response**: `contracts/authority-merge-group-response.schema.json`

## GET `/admin/authority/agent-aliases`
**Purpose**: list author alias dictionary entries.  
**Query Params**: `limit` (int, optional), `q` (string, optional), `status` (string, optional)  
**Response**: `contracts/agent-alias-list-response.schema.json`

## POST `/admin/authority/agent-aliases`
**Purpose**: upsert an author alias entry.  
**Request**: `contracts/agent-alias-upsert-request.schema.json`  
**Response**: `contracts/agent-alias-response.schema.json`

## DELETE `/admin/authority/agent-aliases/{id}`
**Purpose**: delete (soft) an author alias entry.  
**Response**: `contracts/agent-alias-response.schema.json`

# 1.5) Index Writer Service (Internal)

**Responsibility**: managed reindex jobs (state machine, pause/resume/checkpoint).

## Base URL (Local)
`http://localhost:8090`

## POST `/internal/index/reindex-jobs`
**Purpose**: create a reindex job.  
**Request**: `contracts/reindex-job-create-request.schema.json`  
**Response**: `contracts/reindex-job-response.schema.json`

## GET `/internal/index/reindex-jobs/{id}`
**Purpose**: fetch job detail.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/pause`
**Purpose**: pause a running job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/resume`
**Purpose**: resume a paused job.  
**Response**: `contracts/reindex-job-response.schema.json`

## POST `/internal/index/reindex-jobs/{id}/retry`
**Purpose**: retry a failed job.  
**Response**: `contracts/reindex-job-response.schema.json`

# 2) Query Service (QS)

**Responsibility**: Query normalization, lightweight understanding, and generation of `QueryContext`.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/query/prepare`
**Purpose**: Convert user input into `QueryContext (qc.v1.1)` (primary endpoint).

### Request
**Body (JSON)** — **Preferred (official)**
```json
{
  "query": { "raw": "string" },
  "client": {},
  "user": {}
}
```

- `query.raw` (string, required): raw user query
- `client` (object|null, optional): arbitrary client metadata (locale, app, device)
- `user` (object|null, optional): arbitrary user metadata (user_id, segment)

**Backward compatibility (optional)**
```json
{ "raw": "string" }
```
If supported, the server should treat it as:
```json
{ "query": { "raw": "<raw>" } }
```

### Response
- Contract: `contracts/query-context-v1_1.schema.json`
- Example: `contracts/examples/query-context.sample.json`

### Notes (MVP)
- QS must:
  - normalize `query.raw` deterministically
  - populate `canonicalKey`, `detected`, `slots`, and default blocks
- `trace_id/request_id`:
  - If headers exist, propagate them
  - Otherwise generate them

## POST `/query-context` (Deprecated alias)
**Purpose**: Compatibility alias for `/query/prepare`.

### Request
- Contract: `contracts/query-prepare-request.schema.json`
- Example: `contracts/examples/query-prepare-request.sample.json`

### Response
- Contract: `contracts/query-context-v1_1.schema.json`
- Example: `contracts/examples/query-context.sample.json`

## POST `/query/enhance`
**Purpose**: Run 2-pass gating (spell/rewrite/RAG) and return decision + enhanced query.

### Request
- Contract: `contracts/query-enhance-request.schema.json`
- Example: `contracts/examples/query-enhance-request.sample.json`

### Response
- Contract: `contracts/query-enhance-response.schema.json`
- Example: `contracts/examples/query-enhance-response.sample.json`

## POST `/chat`
**Purpose**: RAG chat orchestration (rewrite → retrieve → generate with citations).

### Request
- Contract: `contracts/chat-request.schema.json`
- Example: `contracts/examples/chat-request.sample.json`

### Response
- Contract: `contracts/chat-response.schema.json`
- Example: `contracts/examples/chat-response.sample.json`

### Streaming (optional)
- `POST /chat?stream=true` or `options.stream=true` returns `text/event-stream`
- Events:
  - `meta`
  - `delta`
  - `error`
  - `done`

## POST `/internal/rag/explain`
**Purpose**: Internal retrieval debug trace (lexical/vector/fused/selected + rerank/rewrite reason codes).

### Request
- Same message/query envelope as `/chat` (internal use)

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "status": "ok",
  "query": {
    "text": "string",
    "locale": "string",
    "canonical_key": "string",
    "rewritten": "string"
  },
  "rewrite": {
    "rewrite_applied": true,
    "rewrite_reason": "RAG_LOW_SCORE",
    "rewrite_strategy": "rewrite"
  },
  "retrieval": {
    "top_n": 40,
    "top_k": 6,
    "lexical": [],
    "vector": [],
    "fused": [],
    "selected": [],
    "rerank": {},
    "took_ms": 12,
    "degraded": false
  },
  "llm_routing": {
    "mode": "json",
    "query_intent": "GENERAL",
    "final_chain": ["primary", "fallback_1"]
  },
  "reason_codes": ["RAG_RERANK_DISABLED"]
}
```

## GET `/internal/chat/providers`
**Purpose**: Internal chat provider routing snapshot (policy + provider stats + cooldown state).

### Response
- Contract: `contracts/chat-provider-snapshot-response.schema.json`
- Example: `contracts/examples/chat-provider-snapshot-response.sample.json`

## GET `/internal/chat/recommend/experiment`
**Purpose**: Internal recommendation experiment diagnostics snapshot (enabled/auto-disabled/block-rate state).

### Response
- Contract: `contracts/chat-recommend-experiment-response.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-response.sample.json`

## POST `/internal/chat/recommend/experiment/reset`
**Purpose**: Internal recommendation experiment state reset (quality counters + auto-disable latch clear).

### Request
```json
{}
```

### Response
- Contract: `contracts/chat-recommend-experiment-reset-response.schema.json`
- Example: `contracts/examples/chat-recommend-experiment-reset-response.sample.json`

## GET `/internal/chat/session/state`
**Purpose**: Internal chat session diagnostics snapshot (fallback count + unresolved context).

### Query
- `session_id` (required): chat session identifier.

### Response
- Contract: `contracts/chat-session-state-response.schema.json`
- Example: `contracts/examples/chat-session-state-response.sample.json`
- `session.unresolved_context`에는 `reason_code` 뿐 아니라 `reason_message`, `next_action`이 포함되어 상담 티켓/재시도 분기 판단에 바로 사용 가능.
- `session.recommended_action`, `session.recommended_message`는 현재 세션 상태(임계치 포함)를 반영한 최종 권장 후속 액션이다.
- `session.episode_memory`는 consent 기반 장기 메모리 스냅샷(`opt_in`, `count`, `items`)을 제공한다.
- `session.recommend_experiment`는 추천 실험 상태(자동 비활성화 여부, 누적 block rate)와 runtime 설정(`diversity_percent`, `quality_min_candidates`, `config_overrides`)을 함께 제공한다.

## POST `/internal/chat/session/reset`
**Purpose**: Internal chat session diagnostics reset (fallback counter + unresolved context clear).

### Request
```json
{
  "session_id": "u:101:default"
}
```

### Response
- Contract: `contracts/chat-session-reset-response.schema.json`
- Example: `contracts/examples/chat-session-reset-response.sample.json`

## GET `/internal/qc/rewrite/failures`
**Purpose**: List curated rewrite failure cases for replay/analysis.

### Response
- Contract: `contracts/query-rewrite-failure-response.schema.json`
- Example: `contracts/examples/query-rewrite-failure-response.sample.json`

---

# 3) Search Service (SS)

**Responsibility**: Retrieval orchestration (OpenSearch BM25/hybrid), filters/facets, and returning hits.

## GET `/health`
**Purpose**: liveness probe  
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/search`
**Purpose**: Execute retrieval using `SearchRequest (v1)` and return `SearchResponse (v1)`.
**Alias**: `POST /internal/search` (service-to-service)

### Request
- Contract: `contracts/search-request.schema.json`
- Example: `contracts/examples/search-request.sample.json`

### Response
- Contract: `contracts/search-response.schema.json`
- Example: `contracts/examples/search-response.sample.json`

### Notes (MVP)
- Primary query text should be `query_context.query.canonical`
- Pagination maps to OpenSearch `from/size`
- If `options.debug == true`, include `debug.query_dsl`
- Lexical retrieval should include multilingual fallback paths (phrase + ngram + contains fallback) so Korean compound-word substrings such as `영어교육`/`문화지도` can still match titles like `초등영어교육의 영미문화지도에 관한 연구`.

## POST `/internal/explain`
**Purpose**: Internal debug variant of search (forces explain/debug flags).

### Request
- Contract: `contracts/search-request.schema.json`

### Response
- Contract: `contracts/search-response.schema.json`

---

# 4) Autocomplete Service (ACS) — Planned

**Responsibility**: Prefix suggestions with low latency (Redis hot prefixes + OpenSearch prefix fallback).

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/autocomplete`
**Purpose**: Return query suggestions for a prefix.
**Alias**: `GET /internal/autocomplete` (service-to-service)

### Request (Query Params)
- `q` (string, required): prefix
- `size` (int, optional, default=10)

### Response (Planned MVP Shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "q": "string",
  "suggestions": [
    { "text": "string", "score": 0.0, "source": "redis|opensearch" }
  ]
}
```

---

# 5) Ranking Service (RS)

**Responsibility**: Re-rank candidate documents (LTR / cross-encoder).

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/rerank`
**Purpose**: Re-rank candidates for a query.
**Alias**: `POST /internal/rank` (service-to-service)

### Request (MVP)
```json
{
  "query": { "text": "string" },
  "candidates": [
    { "doc_id": "string", "features": { "rrf_score": 0.1, "lex_rank": 1, "vec_rank": 2 } }
  ],
  "options": { "size": 10, "debug": false, "rerank": true, "timeout_ms": 200 }
}
```

### Response (MVP)
```json
{
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "hits": [
    { "doc_id": "string", "score": 0.0, "rank": 1, "debug": { "features": { "rrf_score": 0.1 } } }
  ],
  "debug": {
    "feature_set_version": "fs_v1",
    "reason_codes": ["size_capped"]
  }
}
```

---

# 6) Model Inference Service (MIS)

**Responsibility**: Centralized model inference (embeddings, scoring) with versioning and performance controls.

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/ready`
**Response**: `200 OK`
```json
{ "status": "ok|degraded", "models_ready": 0, "models_total": 0 }
```

## GET `/v1/models`
**Purpose**: List model registry state.

### Response
- Contract: `contracts/mis-models-response.schema.json`
- Example: `contracts/examples/mis-models-response.sample.json`

## POST `/v1/score`
**Purpose**: Score query-document pairs (e.g., cross-encoder).

### Request
- Contract: `contracts/mis-score-request.schema.json`
- Example: `contracts/examples/mis-score-request.sample.json`

### Response
- Contract: `contracts/mis-score-response.schema.json`
- Example: `contracts/examples/mis-score-response.sample.json`

## POST `/v1/spell`
**Purpose**: Spell correction for a single query text.

### Request
- Contract: `contracts/mis-spell-request.schema.json`
- Example: `contracts/examples/mis-spell-request.sample.json`

### Response
- Contract: `contracts/mis-spell-response.schema.json`
- Example: `contracts/examples/mis-spell-response.sample.json`

## POST `/embed`
**Purpose**: Generate embeddings for input texts (dev fallback).

### Request (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "texts": ["string"]
}
```

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "vectors": [[0.0, 0.0]]
}
```

---

# 7) LLM Gateway (LLMGW)

**Responsibility**: Centralized LLM calls with keys/quotas/retries/audit/cost control.

## GET `/health`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## GET `/ready`
**Response**: `200 OK`
```json
{ "status": "ok" }
```

## POST `/v1/generate`
**Purpose**: Generate a citation-aware response from context.

### Request (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "messages": [{ "role": "user", "content": "string" }],
  "context": { "chunks": [{ "citation_key": "doc#0", "content": "text" }] },
  "citations_required": true
}
```

### Response (MVP shape)
```json
{
  "version": "v1",
  "trace_id": "string",
  "request_id": "string",
  "model": "string",
  "content": "string",
  "citations": ["doc#0"],
  "tokens": 100,
  "cost_usd": 0.002
}
```

---

# 9) Commerce API (via BFF → Commerce Service)

## User (v1)
- `GET /api/v1/skus?materialId=...`
- `GET /api/v1/skus/{skuId}`
- `GET /api/v1/skus/{skuId}/offers`
- `GET /api/v1/skus/{skuId}/current-offer`
- `GET /api/v1/materials/{materialId}/current-offer`
- `GET /api/v1/home/panels?limit=31&type=EVENT|NOTICE`
- `GET /api/v1/home/collections?limit_per_section=8`
- `GET /api/v1/home/benefits?limit=12`
- `GET /api/v1/home/preorders?limit=12`
- `POST /api/v1/home/preorders/{preorderId}/reserve`
- `GET /api/v1/cart`
- `POST /api/v1/cart/items`
- `PATCH /api/v1/cart/items/{cartItemId}`
- `DELETE /api/v1/cart/items/{cartItemId}`
- `DELETE /api/v1/cart/items`
- `GET /api/v1/checkout`
- `GET /api/v1/addresses`
- `POST /api/v1/addresses`
- `PATCH /api/v1/addresses/{addressId}`
- `POST /api/v1/addresses/{addressId}/default`
- `POST /api/v1/orders`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{orderId}`
- `POST /api/v1/orders/{orderId}/cancel`
- `POST /api/v1/payments`
- `GET /api/v1/payments/{paymentId}`
- `POST /api/v1/payments/{paymentId}/mock/complete`
- `POST /api/v1/payments/webhook/{provider}`
- `POST /api/v1/shipments`
- `POST /api/v1/shipments/{shipmentId}/tracking`
- `POST /api/v1/shipments/{shipmentId}/mock/status`
- `GET /api/v1/shipments/{shipmentId}`
- `GET /api/v1/shipments/by-order/{orderId}`
- `POST /api/v1/refunds`
- `GET /api/v1/refunds/{refundId}`
- `GET /api/v1/refunds/by-order/{orderId}`
- `POST /api/v1/support/tickets`
- `GET /api/v1/support/tickets`
- `GET /api/v1/support/tickets/{ticketId}`
- `GET /api/v1/support/tickets/by-number/{ticketNo}`
- `GET /api/v1/support/tickets/{ticketId}/events`
- `GET /api/v1/my/wishlist`
- `POST /api/v1/my/wishlist`
- `DELETE /api/v1/my/wishlist/{docId}`
- `GET /api/v1/my/comments`
- `POST /api/v1/my/comments`
- `GET /api/v1/my/wallet/points`
- `GET /api/v1/my/wallet/vouchers`
- `GET /api/v1/my/wallet/coupons`
- `GET /api/v1/my/elib`
- `GET /api/v1/my/notifications`
- `POST /api/v1/my/notifications/{notificationId}/read`
- `POST /api/v1/my/notifications/read-all`
- `GET /api/v1/my/notification-preferences`
- `POST /api/v1/my/notification-preferences/{category}`
- `GET /api/v1/my/gifts`
- `GET /api/v1/my/gifts/{giftId}`
- `GET /api/v1/my/inquiries`
- `POST /api/v1/my/inquiries`

### Payment Notes
- `POST /api/v1/payments/{paymentId}/mock/complete`는 `dev` profile에서만 활성화된다.
- 결제 provider 선택 기본값은 `payments.default-provider` 설정으로 제어한다.
- 결제 확정(`CAPTURED`)은 webhook 처리(`POST /api/v1/payments/webhook/{provider}`)에서만 전이된다.

### Payment Create (`POST /api/v1/payments`)
- Request contract: `contracts/payment-create-request.schema.json`
- Request example: `contracts/examples/payment-create-request.sample.json`
- Response contract: `contracts/payment-response.schema.json`
- Response example: `contracts/examples/payment-response.sample.json`
- 확장 필드:
  - `payment.checkout_session_id`
  - `payment.checkout_url`
  - `payment.return_url`
  - `payment.webhook_url`
  - `payment.expires_at`

### Payment Read (`GET /api/v1/payments/{paymentId}`)
- Response contract: `contracts/payment-response.schema.json`

### Payment Webhook (`POST /api/v1/payments/webhook/{provider}`)
- Headers:
  - `X-Event-Id` (optional; 없으면 payload `event_id` 또는 payload hash 사용)
  - `X-Signature` (HMAC SHA-256, provider secret)
- Payload 예시 핵심 필드:
  - `event_id`, `payment_id`, `status`, `provider_payment_id`, `occurred_at`

### Home Events/Notices
- `GET /api/v1/home/panels`
  - Query params
    - `limit` (optional, default `31`, max `100`)
    - `type` (optional: `EVENT` or `NOTICE`)
  - Response fields
    - `items[]`: `item_id`, `type`, `banner_image_url`, `badge`, `title`, `subtitle`, `summary`, `link_url`, `cta_label`, `starts_at`, `ends_at`, `sort_order`
    - `count`, `total_count`

### Home Collections (실데이터 섹션)
- `GET /api/v1/home/collections`
  - Query params
    - `limit_per_section` (optional, default `8`, max `24`)
  - Response fields
    - `sections[]`: `key`(`bestseller|new|editor`), `title`, `note`, `link`, `items[]`
    - `items[]`: `doc_id`, `title_ko`, `authors[]`, `publisher_name`, `issued_year`, `edition_labels[]`
    - `limit_per_section`, `count`
  - Data source
    - `bestseller`: 최근 주문/결제 데이터 집계(order_item + orders + sku)
    - `new`: 발행연도/발행일 기반 최신 도서 + 예약구매 랜딩 연계
    - `editor`: 인문/문학/에세이 계열 주제 신호 + KDC 기반 큐레이션

### Today Benefits (프로모션/할인)
- `GET /api/v1/home/benefits`
  - Query params
    - `limit` (optional, default `12`, max `50`)
  - Response fields
    - `today`: 기준일 (`yyyy-MM-dd`)
    - `items[]`: `item_id`, `benefit_code`, `badge`, `title`, `description`, `discount_type`, `discount_value`, `discount_label`, `min_order_amount`, `max_discount_amount`, `valid_from`, `valid_to`, `daily_limit`, `remaining_daily`, `link_url`, `cta_label`
    - `count`, `total_count`, `limit`
  - Data source
    - `cart_content_item` (`content_type='PROMOTION'`) 실데이터 기반
    - 기간/잔여수량 조건(`valid_from`, `valid_to`, `remaining_daily`)으로 오늘 노출 항목 필터링

### Preorder (예약구매)
- `GET /api/v1/home/preorders`
  - Query params
    - `limit` (optional, default `12`, max `60`)
  - Header
    - `x-user-id` (optional, default `1`)
  - Response fields
    - `items[]`: `preorder_id`, `doc_id`, `title_ko`, `authors`, `publisher_name`, `issued_year`, `preorder_price`, `list_price`, `discount_rate`, `preorder_start_at`, `preorder_end_at`, `release_at`, `reservation_limit`, `reserved_count`, `remaining`, `reserved_by_me`, `reserved_qty`, `badge`, `cta_label`
    - `count`, `total_count`, `limit`
- `POST /api/v1/home/preorders/{preorderId}/reserve`
  - Header
    - `x-user-id` (optional, default `1`)
  - Request body
    - `qty` (optional, default `1`, min `1`, max `10`)
    - `note` (optional)
  - Response fields
    - `reservation`: `reservation_id`, `preorder_id`, `user_id`, `qty`, `status`, `reserved_price`, `reservation_limit`, `reserved_total`, `remaining`, `note`
  - Validation
    - 활성 예약구매 상품만 가능
    - 예약 가능 수량 초과 시 `409 preorder_limit_exceeded`

### Orders (User)
- `GET /api/v1/orders`
  - Response fields
    - `items[]`: base order fields + `item_count`, `primary_item_title`, `primary_item_author`, `primary_item_material_id`, `primary_item_sku_id`
- `GET /api/v1/orders/{orderId}`
  - Response fields
    - `items[]`: base order item fields + `material_id`, `title`, `subtitle`, `author`, `publisher`, `issued_year`, `seller_name`, `format`, `edition`, `pack_size`
- `POST /api/v1/refunds`
  - Refund amount is policy-driven by order status and reason code.
  - Response fields (`refund`):
    - `item_amount`, `shipping_refund_amount`, `return_fee_amount`, `amount`, `policy_code`
  - Current policy summary:
    - `PAID` / `READY_TO_SHIP`: full refund request refunds shipping fee (partial refunds: shipping fee not refunded).
    - `SHIPPED` / `DELIVERED`: seller-fault reasons (`DAMAGED`, `DEFECTIVE`, `WRONG_ITEM`, `LATE_DELIVERY`) waive return fee; customer-remorse reasons apply return fee.
    - Return fee defaults to base/fast shipping fee by shipping mode.

### Support Tickets (User)
- `POST /api/v1/support/tickets`
  - Request fields
    - `orderId` (optional): 문의와 연결할 주문 ID
    - `category` (`GENERAL|ORDER|SHIPPING|REFUND|PAYMENT|ACCOUNT`)
    - `severity` (`LOW|MEDIUM|HIGH|CRITICAL`)
    - `summary` (required)
    - `details` (optional object)
    - `errorCode`, `chatSessionId`, `chatRequestId` (optional)
  - Response fields
    - `ticket`: `ticket_id`, `ticket_no`, `status`, `severity`, `expected_response_at`
    - `expected_response_minutes`
- `GET /api/v1/support/tickets/by-number/{ticketNo}`
  - Returns latest ticket state for owner only.
- `GET /api/v1/support/tickets/{ticketId}/events`
  - Returns lifecycle events (received/status changed, etc.)

### MyPage (User)
- `GET /api/v1/my/wishlist`
  - 관심 도서 목록 조회 (`user_saved_material` + 카탈로그 현재 판매가)
- `POST /api/v1/my/wishlist`
  - 관심 도서 추가 (중복 추가 시 무시)
- `DELETE /api/v1/my/wishlist/{docId}`
  - 관심 도서 삭제
- `GET /api/v1/my/comments`
  - 작성한 코멘트 목록
- `POST /api/v1/my/comments`
  - 코멘트 등록 (배송 완료/구매확정 주문만 허용, 주문당 1회)
- `GET /api/v1/my/wallet/points`
  - 통합 포인트 잔액 + 변동 이력
- `GET /api/v1/my/wallet/vouchers`
  - e교환권 목록
- `GET /api/v1/my/wallet/coupons`
  - 쿠폰 목록
- `GET /api/v1/my/elib`
  - e-라이브러리(전자 보관함) 목록
- `GET /api/v1/my/notifications`
  - 알림 목록 (`category`, `unreadOnly` 필터 지원)
- `POST /api/v1/my/notifications/{notificationId}/read`
  - 알림 1건 읽음 처리
- `POST /api/v1/my/notifications/read-all`
  - 전체 읽음 처리
- `GET /api/v1/my/notification-preferences`
  - 알림 수신 설정 조회
- `POST /api/v1/my/notification-preferences/{category}`
  - 알림 수신 설정 변경
- `GET /api/v1/my/gifts`
  - 선물함 목록
- `GET /api/v1/my/gifts/{giftId}`
  - 선물 상세(도서 목록 포함)
- `GET /api/v1/my/inquiries`
  - 1:1 문의 내역 (`support_ticket` 기반)
- `POST /api/v1/my/inquiries`
  - 1:1 문의 등록 (`support_ticket` 생성)

## Admin (v1)
- `GET /admin/sellers`
- `POST /admin/sellers`
- `PATCH /admin/sellers/{sellerId}`
- `GET /admin/skus`
- `POST /admin/skus`
- `PATCH /admin/skus/{skuId}`
- `GET /admin/offers?sku_id=...`
- `POST /admin/offers`
- `PATCH /admin/offers/{offerId}`
- `GET /admin/inventory/balance?sku_id=...`
- `GET /admin/inventory/ledger?sku_id=...`
- `POST /admin/inventory/adjust`
- `GET /admin/payments?limit=&status=&provider=&from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /admin/payments/{paymentId}`
- `GET /admin/payments/webhook-events?limit=&status=&provider=`
- `GET /admin/payments/{paymentId}/webhook-events`
- `POST /admin/payments/{paymentId}/cancel`
- `POST /admin/payments/webhook-events/{eventId}/retry`
- `GET /admin/refunds`
- `GET /admin/refunds/{refundId}`
- `POST /admin/refunds`
- `POST /admin/refunds/{refundId}/approve`
- `POST /admin/refunds/{refundId}/process`
- `GET /admin/settlements/cycles?limit=&status=&from=YYYY-MM-DD&to=YYYY-MM-DD`
- `POST /admin/settlements/cycles`
- `GET /admin/settlements/cycles/{cycleId}`
- `GET /admin/settlements/cycles/{cycleId}/lines`
- `POST /admin/settlements/cycles/{cycleId}/payouts`
- `GET /admin/settlements/payouts?limit=&status=`
- `POST /admin/settlements/payouts/{payoutId}/retry`
- `GET /admin/settlements/reconciliation?limit=&from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /admin/shipments`
- `GET /admin/shipments/{shipmentId}`
- `POST /admin/shipments/{shipmentId}/label`
- `POST /admin/shipments/{shipmentId}/status`
- `POST /admin/support/tickets/{ticketId}/status`

---

## Minimal Smoke Commands (Local)

### QS: QueryContext
```bash
curl -s -XPOST http://localhost:8001/query/prepare \
  -H "Content-Type: application/json" \
  -H "x-trace-id: trace_demo" \
  -H "x-request-id: req_demo" \
  -d '{"query":{"raw":"해리포터 1권"}}'
```

### QS: QueryContext v1 (prepare)
```bash
curl -s -XPOST http://localhost:8001/query/prepare \
  -H "Content-Type: application/json" \
  -H "x-trace-id: trace_demo" \
  -H "x-request-id: req_demo" \
  -d '{"query":{"raw":"해리포터 Vol.1"}}'
```

### QS: Enhance (gating)
```bash
curl -s -XPOST http://localhost:8001/query/enhance \
  -H "Content-Type: application/json" \
  -d '{"request_id":"req_demo","trace_id":"trace_demo","q_norm":"해리포터 1권","q_nospace":"해리포터1권","detected":{"mode":"normal","is_isbn":false,"has_volume":true,"lang":"ko"},"reason":"ZERO_RESULTS","signals":{"latency_budget_ms":800,"score_gap":0.01}}'
```

### SS: Search (when implemented)
```bash
curl -s -XPOST http://localhost:8002/search \
  -H "Content-Type: application/json" \
  -d @contracts/examples/search-request.sample.json
```
