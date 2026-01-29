# B-0282 — QS `/chat` 오케스트레이션: Rewrite → Retrieve → Rerank → Generate (citations 강제, 스트리밍)

## Goal
Query Service에 **제품형 RAG Chat 파이프라인**을 구현한다.

- 입력 질문을 **rewrite/normalize**
- OpenSearch에서 **BM25/Vector/Hybrid로 chunk retrieval**
- (선택) rerank(MIS/RS 경유)로 topK 정밀화
- LLM으로 답변 생성하되 **citations(출처) 강제**
- 응답은 **스트리밍(SSE)** 지원
- 디버그/재현 가능한 `debug{queries,scores,used_chunks}` 포함(옵션)

## Background
- “챗 UI + LLM”은 포트폴리오 가치가 낮음
- “출처/재현/운영”까지 포함해야 제품형
- citations 강제가 환각을 줄이고 운영 신뢰도를 만든다

## Scope

### 1) Public API (BFF가 앞단이지만, QS 내부 엔드포인트 정의)
- `POST /chat` (또는 `/v1/chat`)
- `GET /chat/stream` 또는 `POST /chat` with `Accept: text/event-stream` (SSE)

### 2) Request/Response schema (v1)

**Request**
```json
{
  "request_id": "req_...",
  "session_id": "s_...",
  "user_id": "u_...(optional)",
  "q": "질문 텍스트",
  "locale": "ko-KR",
  "mode": "rag",
  "options": {
    "stream": true,
    "top_k": 8,
    "retrieval": "hybrid",
    "rerank": true,
    "debug": false
  }
}
```

**Response**
```json
{
  "request_id": "req_...",
  "answer": "....",
  "citations": [
    {
      "chunk_id": "c_001",
      "doc_id": "d_01",
      "title": "문서 제목",
      "heading_path": "섹션 > 하위섹션",
      "source_uri": "…",
      "page": 12,
      "snippet": "하이라이트/근거 스니펫"
    }
  ],
  "used_chunks": ["c_001", "c_010"],
  "debug": {
    "rewrite_query": "…",
    "retrieval_queries": { "bm25": "...", "knn": "..." },
    "scores": [
      { "chunk_id": "c_001", "bm25": 1.2, "vec": 0.7, "rrf": 0.12, "rerank": 0.9 }
    ],
    "pipeline": { "retrieval": "hybrid", "rerank_used": true, "degraded": false }
  }
}
```

### 3) Pipeline steps (필수 순서)
1. **Normalize**: NFKC/공백/특수문자 정리
2. **Rewrite** (선택/게이트): “검색용 질문”으로 축약/명확화
3. **Retrieve**
  - BM25: `docs_doc_read` (highlight)
  - Vector: `docs_vec_read` (knn)
  - Fusion: RRF(기본)
4. **Rerank** (선택)
  - chunk 단위 또는 doc→chunk 재선정
  - MIS/RS 경유 가능
5. **Context packing**
  - 중복 제거, 다양성 확보, 토큰 예산 내 topK
6. **Generate**
  - “컨텍스트 밖 추측 금지”
  - “문장마다 citations 번호”
7. **Return**
  - citations + debug(옵션)

### 4) Safety / Quality guardrails (필수)
- **No-citation answer 금지**
- 근거 부족 시: “자료에 없음 / 추가 정보 요청”으로 답
- Prompt injection 최소 방어:
  - 시스템 규칙 고정
  - 컨텍스트를 “자료”로만 취급(명령으로 취급 금지)
- 비용/지연 제어:
  - rewrite/rerank는 옵션 + timeout 예산

### 5) Observability
- latency breakdown: normalize / rewrite / retrieve / rerank / generate
- counters: no_answer_rate, citations_count, rerank_used_rate, degraded_rate

## Non-goals
- 문서 업로드/인덱싱(=B-0280/B-0281)
- LLM 키/레이트리밋 운영(=B-0283)
- 피드백 집계/평가(=B-0284)

## DoD
- 로컬 샘플 문서로 end-to-end:
  - 질문 → citations 포함 답변 생성
- “컨텍스트 없을 때”:
  - 추측하지 않고 거절 응답
- 스트리밍(SSE) 동작 확인
- debug 플래그로 재현 가능한 정보 출력

## Codex Prompt
```text
Implement QS /chat RAG orchestration:
- Add normalize + optional rewrite + hybrid retrieval (BM25+knn+RRF) using docs_doc/docs_vec aliases.
- Enforce citations: if no supporting chunks, return “not in sources” response.
- Support SSE streaming responses and expose debug pipeline metadata (optional).
- Add metrics/logging for stage latencies and degraded/fallback behavior.
```
