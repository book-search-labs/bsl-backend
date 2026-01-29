# B-0290 — LTR Learning Labeling Job: click/dwell/cart/purchase → relevance label

## Goal
Create a**implicit labels** for LTR learning from the search logs (exit/click/register/baskets/purchase).

- Input:   TBD  ,   TBD  ,   TBD  , (Option)   TBD  ,   TBD  
- Output: label(0~4 grade) for query-doc pair + key for learning subject
- Core: position bias minimum consideration (default version is based on the rule)

## Background
- Copyright © 2019 Implicit feedback. All rights reserved.
- 80% of LTR success

## Scope
### 1) Input event assumptions
- impression:
  - imp_id, request_id, session_id, query_hash, results[{doc_id, position}]
- click:
  - imp_id, doc_id, position, ts
- dwell:
  - imp_id, doc_id, dwell_ms
- (Option) cart/purchase:
  - session_id or user_id, doc_id, ts, order_id

### 2) Label rule (v1)
Example 0~4:
- purchase: 4
- add_to_cart: 3
- click + dwell_ms >= 30s: 2
- Click: 1 year
- impression only: 0

### 3 years ) Output dataset schema (OLAP table recommended)
- `ltr_training_example`:
  - date, query_hash, doc_id, label, position, imp_id
  - session_id(optional), user_id(optional)
  - policy/experiment tags
  - point-in-time join key

### 4) Negative sampling (required)
- Within the same impression:
  - Clicked doc vs non-clicked docs
- Price:
  - negatives max N per query (e.g. 50~200)

### 5 days Data quality checks (required)
- Label Distribution / Measurement
- Example number distribution per query
- Removal of dwell ms abnormalities

## Non-goals
- IPS/interleaving implementation(=B-0291)
- LTR Learning Pipeline(=B-0294)

## DoD
- Last N-day data   TBD   creation success
- Copyright © 2015 - 2018 SQUARE ENIX CO., LTD. All Rights Reserved.
- Leave a Reply Cancel reply
- Scale testing up to 1k queries / thousands examples

## Codex Prompt
Build implicit label generation job:
- Consume/search events in OLAP and generate ltr_training_example with labels 0-4 using click/dwell/cart/purchase rules.
- Include negative sampling from impressions and output partitioned tables by date.
- Add data-quality checks and make the job idempotent for reruns.
