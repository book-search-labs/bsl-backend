# B-0231 — Autocomplete Aggregation Consumer (CTR/Popularity → OpenSearch/Redis)

## Goal
Kafka   TBD  
New *CTR/Popularity aggregates** and reflects the result in OpenSearch(ac candidates) + Redis hot cache**.

- time-decay + smoothing application
- (near-real-time or batch window)
- Safety even in reprocessing/recovery(Floor/Window)

## Background
- The autocomplete quality is improved to have “the suggestion that the chosen suggestion will rise up” loop.
- raw counts only if noise/spam/secret cold-start vulnerable → smoothing/decay core.

## Scope
### 1) Consumer topology
- input topics:
  - `ac_impression`
  - `ac_select`
- state:
  - (Option A) Redis/KeyDB state store
  - (Option B) MySQL aggregate table (per day/time) + upsert
- output:
  - Open BulkSearch   TBD   alias update
  - Redis hot cache invalidate/warm (optional)

### 2) Aggregation model (v1 recommended)
#### Metrics
- `impressions(prefix_norm, suggest_text)`
- `selects(prefix_norm, suggest_text)`
- `ctr = selects / impressions`

#### Smoothing (Beta prior)
- `ctr_smooth = (selects + α) / (impressions + α + β)`
  - Example: α=1, β=20 (Anti-estroporation)

#### Time decay (windowed)
- Recent 7d/30d Weight:
  - `count_7d`, `count_30d`
  - or   TBD   (half-life standard)

### 3) Storage tables (choose one for v1)
#### Option A: MySQL aggregate tables (recommended for auditability)
- `ac_agg_daily(prefix_norm, suggest_text, dt, impressions, selects)`
- `ac_feature(prefix_norm, suggest_text, ctr_smooth_7d, pop_7d, updated_at)`
- upsert keys:
  - (prefix_norm, suggest_text, dt)
  - (prefix_norm, suggest_text)

#### Option B: Redis state only (faster, less audit)
- `HINCRBY` counters + periodic snapshot

### 4) Write-back to OpenSearch
- update fields on `ac_candidates` docs:
  - `ctr_smooth`, `popularity_7d`, `updated_at`
- bulk update throttle + retries
- write target: `ac_write` alias (B-0228)

### 5) Cache interaction (B-0229)
- (v1) cache invalidate on updated keys
- (v1.1) warm trending prefixes

### 6) Idempotency / replay safety
- consumer must handle duplicates:
  - use event id/dedup key
  - (MySQL) unique constraint on (event_type, dedup_key) in a consumed-event table (optional)
  - Minimum: Without Kafka exactly-once option “at-least-once” home + duplicate winding design

## Non-goals
- full schema registry rollout (I-0330)
- admin UI (only in A-0106)

## DoD
- Calculation result output as ac impression/ac select sample event in local
- ctr smooth /popularity is reflected in OpenSearch ac candidates
- Redis hot cache performs minimal invalidate so that it does not stale
- A minimum protection device is applied to prevent water from exploding during the event.

## Observability
- metrics:
  - ac_agg_consume_total, ac_agg_lag
  - ac_feature_update_total, ac_feature_update_fail_total
  - bulk_latency_ms
- dashboards:
  - top prefixes, ctr_smooth distribution, select rate trend

## Codex Prompt
Implement an autocomplete aggregation consumer:
- Consume ac_impression/ac_select events.
- Aggregate impressions/selects per (prefix_norm, suggest_text) with time-decay + Beta smoothing.
- Persist aggregates (MySQL recommended) and write back ctr_smooth/popularity to OpenSearch via ac_write alias using bulk updates.
- Invalidate/warm Redis hot prefix cache as needed.
- Add metrics and replay/duplicate safety measures.
