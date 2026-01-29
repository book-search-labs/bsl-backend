# B-0293 — Point-in-time correctness: Textured snapshot/time matching (Offline/Online Match)

## Goal
To prevent the most common failure caused by LTR learning / evaluation **offline/online feature mismatch**
To create a learning data with the “Figure Value” that existed at the point, we implement the **point-in-time correctness**.

## Background
- Learning the past click with today’s CTR/popularity happens
- This site uses cookies. By continuing to browse the site you are agreeing to our use of cookies.

## Scope
### 1) Feature snapshotting (OLAP recommended)
- One unit snapshot table:
  - `feat_doc_daily(date, doc_id, popularity_7d, ctr_doc, ...)`
  - `feat_qd_daily(date, query_hash, doc_id, ctr_qd, ...)`
- B-0292):
  - Online KV with the latest value
  - Load snapshots to OLAP once a day (or batch)

### 2) Training dataset time-join
- New  TBD  (B-0290)
- join rule:
  - New  TBD   (or   TBD )
- time-join forced in SQL/Popin

### 3) Feature spec single source
- New  TBD  (B-0251)
  - offline builder converts the same / clipping / default

### 4) Validation
- offline vs online sample comparison tool:
  - Comparison of online KV vs date snapshots for same (query, doc)
  - Mimatch rate report

## Non-goals
- Perfect for real-time event-time accuracy (per minute)
- Introduction of complete feature store solution (Feast, etc.)

## DoD
- Created a single feature snapshot
- time-join forced to create learning data
- offline/online mismatch check report has a minimum of 1
- Leak prevention rule is documented

## Codex Prompt
Implement point-in-time correctness:
- Add daily feature snapshot tables in OLAP for doc and query-doc features.
- Ensure LTR training examples time-join to snapshots based on event_date (avoid leakage).
- Use features.yaml as the single source for transformations and provide a validation script to measure offline/online mismatch.
