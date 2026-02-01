# B-0292 — CTR/Popularity 집계 컨슈머(시간감쇠/스무딩) → Feature Store 업데이트

## Goal
검색/자동완성 이벤트를 소비해 **CTR/Popularity 피처를 온라인 서빙용 Feature Store(KV)와 OpenSearch 보조 인덱스에 업데이트**한다.

- 입력: Kafka events
  - `search_impression`, `click`, `dwell`
  - `ac_impression`, `ac_select`
- 출력:
  - `ctr_smooth(query, doc)` 또는 `ctr_smooth(doc)`
  - `popularity_7d`, `popularity_30d`
  - `assist_rate(prefix/query)` (자동완성→검색/클릭 연결)

## Background
- RS/LTR에서 가장 강력한 피처는 CTR/Popularity 계열
- 단, 데이터 희소성 때문에 smoothing(베이지안) + time-decay가 필요

## Scope
### 1) Streaming aggregation (Kafka consumer)
- Consume events and aggregate counters:
  - impressions, clicks, dwell_sum, add_to_cart, purchase(추후)
- Key design:
  - doc-level: `doc_id`
  - query-doc: `query_hash|doc_id`
  - autocomplete: `prefix|candidate_id` or `q_norm`

### 2) Smoothing / decay (v1)
- CTR_smooth 예:
  - ctr = (clicks + α) / (impressions + α + β)
  - α/β는 소량 데이터 보호(예: α=1, β=20)
- Time-decay:
  - 7d/30d 윈도우 유지 또는 지수감쇠(half-life)

### 3) Output sinks
- Feature Store(KV):
  - Redis or dedicated KV(초기 Redis OK)
  - keys:
    - `feat:doc:{doc_id}` → {popularity_7d, ctr_doc, …}
    - `feat:qd:{query_hash}:{doc_id}` → {ctr_qd, …}
- OpenSearch:
  - `ac_candidates` or `books_doc`의 popularity 필드(선택)
  - 단, write amplification 주의(배치 업데이트 권장)

### 4) Exactly-once-ish / Idempotency
- consumer offset 관리
- event dedup:
  - `dedup_key`를 사용하거나 (Outbox 기반이면 더 안정)
  - 이벤트에 `event_id` 포함 → 최근 window dedup 캐시(옵션)

### 5) Metrics
- lag, process_rate, drop_rate
- feature 업데이트 성공/실패 카운트

## Non-goals
- 완전한 실시간 개인화 피처
- 고급 attribution (multi-touch)

## DoD
- Kafka로부터 이벤트를 소비해 집계값이 KV에 반영된다
- 스무딩/감쇠가 적용된 CTR/Popularity를 조회 가능
- 재시작/재처리 시 중복 반영이 통제된다(멱등키 or dedup)
- RS에서 이 피처를 읽어 사용할 수 있는 인터페이스 제공(B-0250와 연결)

## Codex Prompt
Build aggregation consumer for CTR/popularity:
- Consume search/ac events from Kafka and maintain rolling stats (7d/30d) with smoothing + decay.
- Write results to Feature Store (Redis KV) with well-defined keys for doc and query-doc features.
- Add idempotency/dedup handling and expose metrics for lag and update failures.
