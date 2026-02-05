# B-0231 — Autocomplete Aggregation Consumer (CTR/Popularity → OpenSearch/Redis)

## Goal
Kafka(또는 outbox relay 후 Kafka)의 `ac_impression/ac_select`를 소비해서
**CTR/Popularity를 집계**하고, 결과를 **OpenSearch(ac_candidates) + Redis hot cache**에 반영한다.

- time-decay + smoothing 적용
- 주기적 반영(near-real-time or batch window)
- 재처리/중복에도 안전(멱등/윈도우)

## Background
- autocomplete 품질은 “선택된 suggestion이 더 위로 올라가는” 루프가 있어야 개선됨.
- raw counts만 쓰면 노이즈/스팸/초기 cold-start에 취약 → smoothing/decay가 핵심.

## Scope
### 1) Consumer topology
- input topics:
  - `ac_impression`
  - `ac_select`
- state:
  - (옵션 A) Redis/KeyDB state store
  - (옵션 B) MySQL 집계 테이블(일별/시간별) + upsert
- output:
  - OpenSearch `ac_write` alias에 bulk update
  - Redis hot cache invalidate/warm (선택)

### 2) Aggregation model (v1 recommended)
#### Metrics
- `impressions(prefix_norm, suggest_text)`
- `selects(prefix_norm, suggest_text)`
- `ctr = selects / impressions`

#### Smoothing (Beta prior)
- `ctr_smooth = (selects + α) / (impressions + α + β)`
  - 예: α=1, β=20 (초기 과대평가 방지)

#### Time decay (windowed)
- 최근 7d/30d 가중:
  - `count_7d`, `count_30d`
  - 또는 `exp_decay` (half-life 기준)

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
  - use event_id/dedup_key (가능하면 payload에 포함)
  - (MySQL) unique constraint on (event_type, dedup_key) in a consumed-event table (optional)
  - 최소: Kafka exactly-once 옵션이 없으면 “at-least-once” 가정 + 중복 완화 설계

## Non-goals
- full schema registry rollout (I-0330)
- admin UI (A-0106에서 표시만)

## DoD
- 로컬에서 ac_impression/ac_select 샘플 이벤트로 집계 결과 산출
- ctr_smooth/popularity가 OpenSearch ac_candidates에 반영됨
- Redis hot cache가 stale되지 않도록 최소 invalidate 수행
- 재실행/중복 이벤트에도 수치가 폭발하지 않도록 최소 보호장치 적용

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
