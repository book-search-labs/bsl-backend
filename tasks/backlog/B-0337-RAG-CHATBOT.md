## Chatbot

> 현재 상태 요약(사용자 제공)과 repo 흐름을 기준으로, **아키텍처/운영 관점에서 “다음에 뭘 고도화할지”**를 티켓으로 쪼갠 문서입니다.  
> 핵심 방향: **(1) 진짜 스트리밍**, **(2) RAG 품질(리트리벌/재랭크/게이팅)**, **(3) 관측/평가/데이터루프**.

---

## B-0250 — BFF “가짜 스트리밍” 제거: QS/LLMGW 기반 **진짜 SSE 스트리밍** end-to-end

### Goal
현재 BFF가 응답을 split해서 SSE를 “흉내”내는 구조를 없애고, **QS가 생성 토큰을 스트리밍**하면 BFF는 **그대로 pass-through**한다.

### Background (현재)
- BFF: `stream=true`이면 **QS의 완성 응답을 받은 뒤** 토큰 단위로 쪼개 emitter로 흘림(진짜 streaming 아님)
- QS: LLMGW `/v1/generate` 호출 후 결과 수신 → 응답 반환(비스트림)

### Scope
- QS `/chat`에 `options.stream=true` 지원 추가
  - LLMGW가 스트리밍을 지원하면: QS가 provider stream을 받아 **SSE로 중계**
  - LLMGW가 비스트림이면: QS는 기존처럼 한번에 받고, BFF는 **더 이상 split하지 않고** 단일 SSE event로 내려도 됨(최소 변경)
- BFF `/chat`의 SSE 로직 변경
  - “split streaming” 제거
  - downstream(QS)에서 SSE면 **바이패스 프록시**
- Contract 정리
  - stream일 때 event 타입/필드(예: `delta`, `done`, `error`) 최소 스펙 정의

### Acceptance Criteria
- 스트림 요청 시 **첫 토큰까지의 latency**가 실제로 줄어든다(로그/metrics).
- BFF는 QS 응답을 쪼개지 않는다.
- 비스트림 모드 동작은 기존과 동일.

---

## B-0251 — QS RAG Retrieval Debug/Explain API 추가 (Admin/Playground용)

### Goal
“왜 이런 답이 나왔는지”를 디버그할 수 있게, QS가 선택한 chunk/score/fusion 과정을 **설명 가능한 형태로 노출**한다.

### Scope
- QS 내부 `retrieve_chunks()` 결과에 대해:
  - lexical topN, vector topN, fused(RRF) topK
  - 각 chunk의 `chunk_id`, `doc_id`, `source_title`, `score`, `rank`, `snippet`
- 신규 엔드포인트(내부용)
  - `POST /internal/rag/explain` (또는 `/chat/explain`)
  - 입력: messages/query, options(topN/topK), locale
  - 출력: retrieval trace + 최종 선택 chunk + reason codes
- 보안: 내부망 전용(서비스 간 호출/관리자 전용), 기본 debug off

### Acceptance Criteria
- 동일 질의에 대해 어떤 chunk가 왜 선택됐는지 확인 가능.
- “chunk가 없어서 fallback”인 경우에도, **검색 시도/결과 0**이 명확히 남는다.

---

## B-0252 — RAG Chunk **Rerank** 단계 추가 (optional): topN → topK 정밀화

### Goal
현재 QS는 lexical+vector를 RRF로 fuse해서 바로 topK를 쓰는 구조인데, 여기에 **재랭크(정밀 스코어링)** 단계를 추가해 근거 chunk 품질을 올린다.

### Scope
- 흐름
  1) retrieve: lexical+vector → fuse → 후보 topN
  2) rerank: 후보 topN을 MIS(또는 RS)에 보내 topK 선택
  3) 최종 topK를 citations 근거로 사용
- 구현 옵션
  - (A) QS → MIS `/v1/score` (task=`rag_rerank` 또는 `rerank`)
  - (B) QS → RS `/internal/rank` 재사용(가능하면)
- 가드레일
  - timeout/budget 부족하면 rerank skip하고 fused 결과 사용
  - debug에 `rerank_skipped_reason` 기록

### Acceptance Criteria
- rerank on/off 비교가 가능(옵션/환경변수).
- rerank 실패 시에도 chat은 정상 응답(degrade-safe).

---

## B-0253 — “검색 결과가 나쁠 때만” Query Rewrite 연동 (RAG용 2-pass)

### Goal
처음 retrieval이 부실할 때만, QS가 **rewrite를 한 번 더 시도**해서 retrieval을 개선한다(항상 2번 검색하지 않음).

### Scope
- “나쁨” 판단(초기 규칙)
  - 후보 chunk 0개
  - fused topK의 score가 임계값 이하
  - diversity 낮음(거의 동일한 문서/시리즈만 반복)
- 2-pass 전략
  1) pass1: 원문 query로 retrieve
  2) bad이면: `run_rewrite(... candidates=retrieve_candidates(...))` 또는 `/query/enhance` 로 rewrite 획득
  3) pass2: rewritten query로 **한 번만** 재-retrieve
- degrade
  - rewrite 실패/거절이면 pass1 결과로 진행
- debug
  - `rewrite_applied`, `rewrite_reason`, `rewrite_strategy`

### Acceptance Criteria
- “후보 0개” 케이스에서 rewrite가 실행되고, pass2로 후보가 늘어나는 사례가 확인된다.
- 후보가 충분한 일반 케이스에서는 pass2가 실행되지 않는다.

---

## B-0254 — RAG Retrieval/Answer Cache 도입 (canonical_key 기반)

### Goal
동일/유사 질문이 반복될 때 비용과 지연을 줄이기 위해 캐시를 추가한다.

### Scope
- 캐시 계층 2개
  1) Retrieval cache: `rag:ret:{canonical_key}` → topK chunks(+citations seed)
  2) Answer cache(선택): `rag:ans:{canonical_key}:{prompt_version}` → final answer(짧은 TTL)
- TTL: 1~10분(환경변수), locale 포함
- Cache invalidation(초기)
  - TTL 기반만 우선 적용 (정교한 invalidation은 나중)

### Acceptance Criteria
- 동일 질문 반복 시 retrieval latency/LLM 호출 빈도 감소.
- 캐시 장애 시에도 정상 degrade.

---

## B-0255 — Citations 스키마 강화 (chunk_id ↔ citation 매핑 강제)

### Goal
현재 “citation이 없으면 fallback”은 좋지만, **citation의 정합성(실제 chunk와 연결)**을 강제해야 운영에서 신뢰도가 올라간다.

### Scope
- chunk에 안정적인 식별자 부여
  - `chunk_id`(index writer에서 생성) + `doc_id` + `offset`
- LLM prompt/response 스키마
  - 응답은 `{answer, citations:[{chunk_id, quote?, url?, title?}]}` 형태를 강제
- post-check
  - citations의 `chunk_id`가 retrieval set에 없으면: fallback 또는 citations 재생성(후처리)

### Acceptance Criteria
- 응답의 citations는 항상 **retrieved chunk_id**와 매핑된다.
- 매핑 실패는 명확한 reason code로 기록된다.

---

## B-0256 — Chat 관측/운영 지표 추가 (latency budget + reason codes)

### Goal
“왜 느려졌는지/왜 fallback했는지”가 한눈에 보이게 metrics/logs를 표준화한다.

### Scope
- Metrics(예시)
  - `chat_requests_total{decision}`
  - `rag_retrieve_latency_ms`
  - `llm_generate_latency_ms`
  - `rag_chunks_found_count`
  - `chat_fallback_total{reason}`
- 표준 reason code
  - `NO_MESSAGES`, `RAG_NO_CHUNKS`, `LLM_NO_CITATIONS`, `BUDGET_EXCEEDED`, `PROVIDER_TIMEOUT` ...
- Trace propagation
  - BFF → QS → LLMGW trace headers 일관성 확인

### Acceptance Criteria
- fallback이 발생한 이유가 metrics/log에 남는다.
- p95/p99가 어느 단계에서 발생했는지 분해 가능하다.

---

## B-0257 — Chat Feedback → 학습/평가 데이터로 정규화 (OLAP용)

### Goal
이미 존재하는 `/chat/feedback` + outbox를 활용해 “질문-답변-근거-피드백” 데이터를 평가/개선 루프로 연결한다.

### Scope
- outbox event 스키마 확장(또는 신규 타입)
  - `chat_request`, `chat_response`, `chat_feedback`
  - 공통 키: `conversation_id`, `request_id`, `trace_id`, `canonical_key`, `used_chunk_ids`
- ClickHouse 테이블 설계 초안
  - `chat_sessions`, `chat_turns`, `chat_feedbacks`
- 간단 리포트 쿼리
  - thumbs down 비율 높은 질문 topN
  - citations 부족으로 fallback된 비율

### Acceptance Criteria
- 피드백 이벤트가 OLAP으로 적재되고, 기본 리포트 쿼리가 동작한다.
- “어떤 chunk를 근거로 썼는지”가 저장된다.

---

# 추천 적용 순서 (리스크/효과 기준)
1) **B-0256(관측)** → 2) **B-0250(진짜 스트리밍)** → 3) **B-0251(explain)**
4) **B-0252(rag rerank)** → 5) **B-0253(2-pass rewrite)** → 6) **B-0255(citation 정합성)**
7) **B-0254(cache)** → 8) **B-0257(피드백 루프)**
