# B-0292 — CTR/Popularity Aggregation Contactor (Time Detection / Smoothing) → Feature Store Update

## Goal
CTR/Popularity feature Store (KV) and OpenSearch support indexes are updated.

- Event
  - `search_impression`, `click`, `dwell`
  - `ac_impression`, `ac_select`
- Output:
  - New  TBD   or   TBD  
  - `popularity_7d`, `popularity_30d`
  - New  TBD   (Autocomplete→Search/Click Connect)

## Background
- The most powerful feature of RS/LTR is the CTR/Popularity family
- + time-decay

## Scope
### 1) Streaming aggregation (Kafka consumer)
- Consume events and aggregate counters:
  - ', enableHover: false, enableTracking: true, buttons:{layout: 'box count'}, click: function(api, options){ api.simulateClick(); api.openPopup('facebook'); } }); $('#googleplus').sharrre({ share: { googlePlus: true }, template: '
- Key design:
  - doc-level: `doc_id`
  - query-doc: `query_hash|doc_id`
  - autocomplete: `prefix|candidate_id` or `q_norm`

### 2) Smoothing / decay (v1)
- CTR smooth Example:
  - ctr = (clicks + α) / (impressions + α + β)
  - α/β is a small amount of data protection (e.g. α=1, β=20)
- Time-decay:
  - 7d/30d Windows Maintenance or Half-life

### 3) Output sinks
- Feature Store(KV):
  - Redis or KV(초기 Redis OK)
  - keys:
    - `feat:doc:{doc_id}` → {popularity_7d, ctr_doc, …}
    - `feat:qd:{query_hash}:{doc_id}` → {ctr_qd, …}
- OpenSearch:
  - New  TBD   or   TBD   Popularity field(optional)
  - write amplification Notes (Recommended for batch updates)

### 4) Exactly-once-ish / Idempotency
- consumer offset management
- event dedup:
  -  TBD  
  - Event   TBD  Included → Recent Window dedup cache(option)

### 5) Metrics
- lag, process_rate, drop_rate
- feature update success/pack count

## Non-goals
- Real-time personalization feature
- Advanced attribution (multi-touch)

## DoD
- The aggregate value is reflected in KV, which consumes events from Kafka
- CTR/Popularity
- Re-start/reprocessing is controlled by redundancy reflector (left light key or dedup)
- Provides an interface that reads this feature in RS (connects with B-0250)

## Codex Prompt
Build aggregation consumer for CTR/popularity:
- Consume search/ac events from Kafka and maintain rolling stats (7d/30d) with smoothing + decay.
- Write results to Feature Store (Redis KV) with well-defined keys for doc and query-doc features.
- Add idempotency/dedup handling and expose metrics for lag and update failures.
