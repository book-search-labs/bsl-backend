# B-0300 — Designated by Material (Platform/Set/Recurrer) + SERP Grouping

## Goal
When the same “work/series” exists in multiple documents, such as document/recurer/set/released,
- In search results ** Reduce duplicate exposure**
- For users, you can see “Primary” + variations (Variants)** structure.

## Why
- “The same book looks many times” issues with UX/CTR/Ranking learning.
- Authority/merge is the largest in search quality.

## Scope
### 1) Canonical key design (work unit)
- New  TBD   Generating Rules (Ultra heuristic):
  - normalize(title) + normalize(main_author) + (series_key optional)
  - volume information is included in work key/included policy clarification (the ticket is in series)
- Storage on DB:
  - `material.work_key`, `material.work_key_confidence`

### 2) Merge/Group model
-  TBD  (CEO) +   TBD  (Fold) Table (or material merge extension)
- Title:
  - Sales/Registration/Registration/Registration/Registration/Registration
- Tag:
  - Cover/edition/publisher/format Factory Tour

### 3 years SERP Grouping
- book doc News
  - `work_key`, `is_primary`, `primary_doc_id`, `variant_count`
- In SR:
  - Default Search   TBD   (OS field collapsing available)
  - variants attach after work key standard dedup with post-process

### 4 days ago ) Book detail extension (CEO/Explosion)
- New  TBD  in:
  - Primary + variants

## Non-goals
- Full ML-based entity resolution
- merging all cases perfectly (in the first term “the worst” improvement)

## DoD
- work key is created (ETL or batch) reflected in DB/Index
- In search results, the same work key duplicate impressions can be reduced
- Can be checked in book detail
- Rules/Purposes are documented and fixed with regression tests (Sample queries)

## Codex Prompt
Implement authority grouping for materials:
- Create work_key heuristic and persist it to canonical DB.
- Build primary/variant grouping and selection rules (metadata completeness + popularity).
- Reflect grouping fields in OpenSearch and implement SERP dedup/collapse by work_key.
- Extend book detail to show variants and document rules + regression sample queries.
