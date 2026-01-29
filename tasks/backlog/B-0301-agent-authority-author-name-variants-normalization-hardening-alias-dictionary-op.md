# B-0301 — Agent authority (lower notation strain) Normalization Altitude + alias pre-operation

## Goal
The author's name is “Kim Young-ha”, which solves the problems that are marked variously.
- Search Matching Stabilization (title/author field)
- Reduction of uniform results
- Recommendation/Entipreneurship Improvement

## Scope
### 1) Agent canonicalization
- New  TBD  Certificate
- New  TBD   table introduction (or existing structure extension):
  - `agent_id`, `alias`, `alias_norm`, `source`, `confidence`, `created_at`

### 2) Alias creation logic (based on the initial rule)
- normalize rules:
  - NFKC/Public bag/Public store removal, Lower English, Korean/English conversion options
- Payment Terms:
  - NLK source attributes (multi-language labels)
  - Rule-based strains (whispering/hardening)
  - Operator Manual Registration (Admin UI from A-0130)

### 3) Using Search/Query extension
- QS:
  - Detect “author intent” allows the alias candidate to expand hints
- SR:
  - alias alias
- Index:
  - book doc   TBD  or   TBD   + join Strategy(optional)

### 4) Quality guard
- Payment Terms:
  - low alias boost
  - Operational Queue when collision (alias maps multiple agent)

## Non-goals
- Massive external authority DB integration (VIAF, etc.) — follow
- Fully automatic disambiguation(manual perfect solution)

## DoD
- agent alias
- Improved the notational case in the author search (Sample query regression)
- Collision/Expansion alias drops queue and operators can check (A-0130 connection)

## Codex Prompt
Implement agent authority and alias dictionary:
- Add agent_alias table and canonical_name normalization rules.
- Generate aliases from source labels + heuristic variants, with confidence and collision handling.
- Use aliases in QS/SR for author-intent queries and update OpenSearch mapping accordingly.
- Add regression samples and a workflow for conflict review (to be wired to Admin UI later).
