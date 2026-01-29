# B-0282 — QS   TBD   Occuration: Rewrite → Retrieve → Rerank → Generate (citations forced, streaming)

## Goal
Query Service ** implementation of product type RAG Chat pipeline**

- Rewrite/normalize
- chunk retrieval
- TopK Precisionization with rerank(MIS/RS)
- citations(Source) Force**
- SSE Support
- Debug/Reusable   TBD   Included(Optional)

## Background
- “Chat UI + LLM” lowers portfolio value
- Product type that should be included to “Export/Restore/operation”
- citations to reduce the severity and make operational reliability

## Scope

### 1) Public API (BFF is front, but QS internal endpoint definition)
- New  TBD   (or   TBD  )
- New  TBD   or   TBD   with   TBD   (SSE)

### 2) Request/Response schema (v1)

**Request**
```json
{
  "request_id": "req_...",
  "session_id": "s_...",
  "user_id": "u_...(optional)",
"q": "text text",
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
"title": "Text title",
"heading path": "Section > Subsection",
      "source_uri": "…",
      "page": 12,
"snippet": "Highlight/Register Snippet"
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

### 3) Pipeline steps (required order)
1. New *Normalize**: NFKC/Release/Release
2. New *Rewrite** (Optional/gate): “Search questions” to aggregate/clearize
3. **Retrieve**
  - BM25: `docs_doc_read` (highlight)
  - Vector: `docs_vec_read` (knn)
  - Fusion: RRF
4. New *Rerank** (optional)
  - chunk unit or doc→chunk reel
  - MIS/RS
5. **Context packing**
  - Remove duplicates, securing diversity, topK within token budget
6. **Generate**
  - “Prohibiting outside context”
  - “citations number per statement”
7. **Return**
  - citations + debug(optional)

### Quality Guardrails
- New *No-citation answer prohibition**
- When lacking: “No data / Request for additional information”
- Prompt injection minimum defense:
  - Fixed system rules
  - Context handles only as “Data” (Prohibition of handling with the command)
- Payment Terms:
  - rewrite/rerank options + timeout budget

### 5) Observability
- latency breakdown: normalize / rewrite / retrieve / rerank / generate
- counters: no_answer_rate, citations_count, rerank_used_rate, degraded_rate

## Non-goals
- Document upload / indexing(=B-0280/B-0281)
- LLM Key/Late Limit Operation(=B-0283)
- Feedback Accounting/Rating(=B-0284)

## DoD
- end-to-end with local sample documents:
  - Question → Generate a response containing citations
- “No context”:
  - Rejection response without guessing
- Streaming (SSE) Motion
- printable information with debug flags

## Codex Prompt
```text
Implement QS /chat RAG orchestration:
- Add normalize + optional rewrite + hybrid retrieval (BM25+knn+RRF) using docs_doc/docs_vec aliases.
- Enforce citations: if no supporting chunks, return “not in sources” response.
- Support SSE streaming responses and expose debug pipeline metadata (optional).
- Add metrics/logging for stage latencies and degraded/fallback behavior.
```
