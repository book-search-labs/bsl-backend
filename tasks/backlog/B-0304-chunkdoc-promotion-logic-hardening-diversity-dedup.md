# B-0304 — Chunk→Doc Winning Loom Altitude (Remove Versatile/Remove Duplicate)

## Goal
because Vector retrieval is out of chunk-level,
New *Promote as a doc-level candidate for chunk results**
- Multiple chunks of specific documents prevent the issue of clarifying the upper right
- We use cookies to ensure that we give you the best experience on our website.
- High rerank input quality.

## Why
- naive shoot: doc id of the topK chunks only happens
- If rerank is limited to topR=50, the candidate variety reduces the quality

## Scope
### 1) Promotion algorithm
Input:   TBD   
Output:   TBD   

Basic Rules (Registration v1):
- doc-by-**best chunk score** used as a representative score
- limit chunk count per doc (e.g. up to 2 million archives)
- doc_score = best_chunk_score (+ small bonus for multiple good chunks, capped)

### 2) Diversity Pharmaceuticals
- In the doc-level results:
  - Same series/work key(when it is) excessive exposure suppression(cap)
  - same author id expose suppression(cap)
- The complex technique like MMR is v2 and v1 is enough to cap+penalty

### 3) Select Snippet/Context
- Text to enter rerank input:
  - best_chunk snippet + title/author + optional description
- doc, doc, doc, doc, doc, doc, doc, doc

### 4) Fusion phase connection
- Rank/score from vector docs to be stable:
  - Normalization(optional)
  - fusion input after cut to topM docs

## Non-goals
- Optimization of full MMR/semantic diversity (extra)
- chunk-level rerank

## DoD
- Vector candidate doc Diversity Improved (Delete doc derivatives)
- doc context in rerank(CEO chunk)
- debug(doc score configuration, chunk optional)

## Codex Prompt
Improve chunk-to-doc promotion:
- Aggregate chunk results into doc candidates using best_chunk_score with capped multi-chunk bonuses.
- Add diversity caps by work_key/series/author to prevent over-concentration.
- Select a stable representative chunk snippet per doc for rerank input, with debug visibility.
- Integrate into SR hybrid pipeline before fusion and rerank stages.
