# B-0228 — Autocomplete Index/Alias Strategy (ac_candidates_v*, ac_read/ac_write)

## Goal
OpenSearch indexes are standardized by the version + alias** for Autocomplete operations.
- `ac_candidates_v*` (write target)
- New  TBD   /   TBD   alias separation
- stable serving during reindex
- CTR/popularity

## Background
- The AC is tight, and the index change is frequent.
- If you attach to direct index without alias:
  - Colored/rollback time downtime
  - Difficult to change mapping during operation

## Scope
### 1) Index set definition
- New  TBD   (mapping fixed)
  - fields:
    - New  TBD    (keyword / edge ngram-based)
    - `suggest_text` (keyword/text)
    - `popularity_7d`, `ctr_smooth`
    - `updated_at`
    - (optional)   TBD  ,   TBD  ,   TBD  
- Aliases:
  - New  TBD   → Current serving index
  - New  TBD   → Index/Update Target Index

### 2) Write flow (2 patterns)
- Pattern A
  - New   TBD   creation
  - Bulk load (default candidate + aggregate)
  - New  TBD   Swap
  - old retention
- Pattern B (in-place update)
  -  TBD  to update/upsert
  - If you need to change mapping, then to A

### 3) Validation / smoke
- alias always point one index
- read/write alias kinetic check

## Non-goals
- synonym/normalization deployment(=B-0224)
- Redis hot cache(=B-0229)

## DoD
- Template/Poping and alias creation script exists
- ac read/ac write switch (withrunbook) available
- Documentation of the rollback procedure (previous version alias recovery)

## Observability
- index version tag
- alias target

## Codex Prompt
Define OpenSearch autocomplete index versioning + alias scheme:
- Create ac_candidates_v1 mapping + template.
- Create aliases ac_read and ac_write with safe swap scripts.
- Provide validation checks and rollback procedure in docs/runbook.
