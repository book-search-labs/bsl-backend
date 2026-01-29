# B-0283 — LLM Gateway: 키/레이트리밋/리트라이/감사/비용 통제(중앙화)

## Goal
LLM 호출을 QS 내부에 흩뿌리지 않고, **단일 LLM Gateway 레이어**로 중앙화한다.

- API key/secret 관리
- rate-limit / concurrency 제한
- retry/backoff, timeout, circuit breaker
- request/response 감사로그(민감정보 마스킹)
- 비용 추적(토큰/요금 추정) + 예산 제어

## Background
- LLM은 운영에서 “보안/비용/장애 전파”의 핵심 리스크
- 중앙화하면:
  - 키 유출 위험 감소
  - 비용/레이트리밋 정책 일관화
  - 장애 시 degrade 정책 적용 쉬움

## Scope
### 1) Internal API
- `POST /internal/llm/chat-completions`
- `POST /internal/llm/embeddings` (선택, B-0266a/Hybrid와 연결 가능)

Request 공통 메타:
- request_id, trace_id, user_id(optional), purpose(enum: RAG_ANSWER/QUERY_REWRITE/SPELL/…)
- model_name, temperature, max_tokens, timeout_ms

### 2) Policies (필수)
- per-purpose budget:
  - rewrite: max_tokens 낮게
  - answer: max_tokens 중간
- rate limits:
  - per-IP, per-user, per-purpose
- timeouts:
  - hard timeout
- retries:
  - 429/5xx는 backoff
  - 4xx는 no-retry

### 3) Audit & Masking (필수)
- 저장 시:
  - prompt/response 원문 저장은 옵션(기본 off)
  - 저장하더라도 PII 마스킹 규칙 적용
- `audit_log` 또는 별도 `llm_audit_log` (선호)
  - request_id/trace_id, model, tokens, latency, status

### 4) Degrade rules
- gateway circuit open → QS는 “근거 기반 요약만/혹은 답변 거절”로 degrade
- rewrite 실패 → 원문 q로 retrieval 진행

### 5) Observability
- tokens_used, cost_estimate, error_rate, retry_count, latency_p95/p99

## Non-goals
- Admin 비용 대시보드(추후 I-0306/Metabase로)
- 완전한 멀티 벤더 라우팅(하지만 확장 가능하게 설계)

## DoD
- QS에서 LLM 호출이 모두 Gateway를 통해서만 발생
- rate-limit/timeout/retry/circuit 정책 동작
- 감사로그(요약 메타) 저장
- 토큰/비용 지표 노출

## Codex Prompt
Create LLM Gateway module/service:
- Centralize chat-completions (and optionally embeddings) calls with rate limits, retries, timeouts, and circuit breaker.
- Emit audit logs with request_id/trace_id and token/cost estimates, applying masking rules.
- Update QS to call only through this gateway and implement degrade behavior on gateway failures.
