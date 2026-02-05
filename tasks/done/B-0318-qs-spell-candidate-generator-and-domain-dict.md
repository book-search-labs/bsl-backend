# File: tasks/backlog/B-0318-qs-spell-candidate-generator-and-domain-dict.md

# B-0318 — QS: Spell Candidate Generator (keyboard/edit-distance) + Domain Dictionary (alias)

## Goal
Improve spell correction robustness and reduce reliance on expensive seq2seq models by adding a cheap candidate-generation layer:
- keyboard-adjacency typos
- edit-distance candidates
- domain dictionary (author/title/publisher aliases)
  This feeds into the final spell decision (MIS T5 or rule-based) and increases accept-rate without harming precision.

## Background / Current State
- QS spell is provider-based; we plan to use MIS /v1/spell for real correction.
- Pure model-based spell often over-corrects in domain queries (ISBN/volume/series tokens).
- Big-tech style spell often uses:
  1) candidate generation (cheap)
  2) scoring/selection (model or LM)
  3) guardrails

## Scope
### 1) Candidate Generation in QS (cheap, deterministic)
Implement `SpellCandidateGenerator` that produces N candidates from `q_norm`:
- Keyboard adjacency (KR 2-set + EN QWERTY)
- Whitespace/merge/split fixes
- Common romanization / spacing patterns (optional)
- Edit distance (Levenshtein <= 1~2 per token, bounded by max candidates)

### 2) Domain Dictionary (author/title/publisher aliases)
Add a simple domain alias store and query it during candidate generation:
- Data source option A: local TSV/JSON file under `data/dict/`
- Data source option B: Redis hash/set
- Data source option C: MySQL table (later), but for now file or Redis is fine

Dictionary entries:
- key: canonical form
- values: variants/synonyms/typo variants
- type: AUTHOR | TITLE | PUBLISHER | SERIES | KEYWORD

### 3) Candidate Scoring/Selection (QS-side)
Add a lightweight scorer for candidates before calling MIS:
- penalty for too-large edits
- preserve digits/ISBN/volume tokens
- prefer candidates that reduce OOV signals (if available from analyzer)
  Output:
- top K candidates (e.g., 5) with scores and reasons

### 4) Integration with Enhance Pipeline
- In enhance flow, if strategy involves SPELL:
  - generate candidates first
  - optionally send best candidate(s) to MIS /v1/spell as the input
  - OR send original text but keep candidates as fallback options
- Store candidate list in debug payload for replay/debugging
- Cache candidate-generation results under enhance cache payload

## Non-goals
- Full trie/DAWG dictionary search (later optimization)
- Training a new spell model
- UI changes (Admin debug UI is separate)

## API / Debug fields
Enhance response should include:
- spell.candidates[] (optional when debug=true)
  - { "text": "...", "score": 0.71, "reason": ["kbd_adj","edit1","dict_hit"] }

## Config (env)
- QS_SPELL_CANDIDATE_ENABLE=1
- QS_SPELL_CANDIDATE_MAX=50
- QS_SPELL_CANDIDATE_TOPK=5
- QS_SPELL_DICT_PATH=data/dict/spell_aliases.jsonl
- QS_SPELL_DICT_BACKEND=file|redis
- QS_SPELL_DICT_REDIS_URL=...
- QS_SPELL_EDIT_DISTANCE_MAX=2
- QS_SPELL_KEYBOARD_LOCALE=ko|en|both

## DoD
- Candidate generator produces reasonable candidates for:
  - 붙여쓰기/띄어쓰기
  - 자판 인접 오타
  - author/title variants via dictionary
- Guardrails prevent numeric/ISBN/volume corruption
- Unit tests cover:
  - keyboard adjacency generation
  - edit distance boundedness
  - dictionary hit path
  - caching path
- Docs include a small starter dictionary file example

## Files to Change (expected)
- `services/query-service/app/core/spell_candidates.py` (new)
- `services/query-service/app/core/spell.py` (integration)
- `services/query-service/app/core/enhance.py` (integration)
- `services/query-service/app/core/analyzer.py` (optional signals)
- `services/query-service/app/core/cache.py` (cache payload)
- `services/query-service/tests/`

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Implement a deterministic spell candidate-generation layer in QS:
keyboard adjacency + edit-distance + domain dictionary.
Integrate it into enhance flow (SPELL strategies), include debug candidates, caching, and tests.
Keep behavior safe with existing guardrails and avoid changing public contracts except adding optional debug fields.
