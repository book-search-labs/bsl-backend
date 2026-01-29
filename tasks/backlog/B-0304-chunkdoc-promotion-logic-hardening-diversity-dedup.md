# B-0304 — Chunk→Doc 승격 로직 고도화(다양성/중복 제거)

## Goal
Vector retrieval이 chunk-level로 나오기 때문에,
**chunk 결과를 doc-level 후보로 승격(promote)** 하는 과정에서
- 특정 문서의 여러 chunk가 상위권을 점령하는 문제를 막고
- 다양한 문서를 후보군에 포함하며
- rerank 입력 품질을 높인다.

## Why
- naive 승격: topK chunks의 doc_id를 모으기만 하면 “한 doc의 chunk 도배”가 발생
- rerank가 topR=50 제한이면 후보 다양성이 줄어 품질이 떨어짐

## Scope
### 1) Promotion 알고리즘
입력: `chunks = [(chunk_id, doc_id, score, snippet, ...)]`
출력: `vector_docs = [(doc_id, doc_score, best_chunk, chunk_hits...)]`

기본 규칙(권장 v1):
- doc별로 **best_chunk_score**를 대표 점수로 사용
- doc별 chunk_count를 제한(예: 최대 2개만 보관)
- doc_score = best_chunk_score (+ small bonus for multiple good chunks, capped)

### 2) Diversity 제약
- doc-level 결과에서:
  - 동일 series/work_key(있으면) 과다 노출 억제(cap)
  - 같은 author_id 과다 노출 억제(cap)
- MMR 같은 복잡한 기법은 v2로 미룸, v1은 cap+penalty로 충분

### 3) Snippet/Context 선택
- rerank 입력에 들어갈 텍스트는:
  - best_chunk snippet + title/author + optional description
- doc당 “대표 chunk”를 1개로 고정(기본), debug로 top chunks 포함 가능

### 4) Fusion 단계 연계
- vector_docs의 rank/score가 안정적으로 나오도록:
  - score normalization(옵션)
  - topM docs로 cut 후 fusion input으로 제공

## Non-goals
- full MMR/semantic diversity 최적화(추후)
- chunk-level rerank(초기 과도)

## DoD
- vector 후보 doc 다양성이 개선됨(한 doc 도배 감소)
- rerank에 들어가는 doc 컨텍스트가 안정적(대표 chunk 일관)
- debug에서 승격 로직 결과를 확인 가능(doc_score 구성, 선택된 chunk)

## Codex Prompt
Improve chunk-to-doc promotion:
- Aggregate chunk results into doc candidates using best_chunk_score with capped multi-chunk bonuses.
- Add diversity caps by work_key/series/author to prevent over-concentration.
- Select a stable representative chunk snippet per doc for rerank input, with debug visibility.
- Integrate into SR hybrid pipeline before fusion and rerank stages.
