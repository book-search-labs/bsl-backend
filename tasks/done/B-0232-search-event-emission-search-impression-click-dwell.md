# B-0232 — Emit Search Events (search_impression / click / dwell) for Ranking/LTR Loop

## Goal
검색 품질(LTR/CTR/feature) 운영 루프를 위해
Search 결과 노출/클릭/체류 이벤트를 **표준 스키마로 발행**한다.

- event types: `search_impression`, `click`, `dwell`
- `imp_id`(impression id) 기반으로 분모/분자/체류를 연결
- experiment/policy/model_version 정보를 이벤트에 포함

## Background
- LTR/오프라인 평가/온라인 지표는 이벤트 품질에 달림.
- 특히 position bias/세션/실험 버킷 정보 없으면 학습이 망가짐.

## Scope
### 1) Event schema (v1 minimum)
#### search_impression
- 발생 시점: SERP 응답을 내려주기 직전
- fields:
  - `event_type`: "search_impression"
  - `event_time`
  - `imp_id` (uuid)
  - `request_id`, `trace_id`, `session_id`, `user_id`(optional)
  - `query`: { `q_raw`, `q_norm`, `q_hash` }
  - `filters`, `sort`, `page`, `size`
  - `results`: [{ `doc_id`, `position`, `score`(optional), `source`(bm25/hybrid), `debug`(optional) }]
  - `pipeline`: { `retrieval`, `fusion`, `rerank`, `model_version` }
  - `experiment`: { `bucket`, `flags` }

#### click
- 발생 시점: 사용자가 결과 클릭(상세 진입)
- fields:
  - `event_type`: "click"
  - `event_time`
  - `imp_id`
  - `doc_id`, `position`
  - `request_id`, `trace_id`, `session_id`, `user_id`
  - (선택) `referrer`: "serp"

#### dwell
- 발생 시점: 상세에서 일정 시간 이상 체류 후(또는 페이지 언로드)
- fields:
  - `event_type`: "dwell"
  - `event_time`
  - `imp_id`
  - `doc_id`
  - `dwell_ms`
  - `request_id`, `trace_id`, `session_id`, `user_id`

### 2) Producer location (recommended)
- **BFF**가 외부 트래픽을 받으므로:
  - `search_impression`: BFF가 SR 응답 수신 후 outbox 기록
  - `click/dwell`: 프론트가 BFF endpoint로 전송 → outbox 기록
- Search Service 내부에서 만들어도 되지만, “단일 진입점” 원칙상 BFF가 깔끔

### 3) imp_id 생성 규칙
- search 요청마다 1개 생성
- 응답 results에 imp_id와 함께 내려주거나,
  click/dwell 요청에 포함될 수 있게 클라이언트에 전달

### 4) dedup_key (outbox idempotency)
- `search_impression`: hash(event_type + imp_id)
- `click`: hash(event_type + imp_id + doc_id)
- `dwell`: hash(event_type + imp_id + doc_id + dwell_bucket)
  - dwell_ms는 변동 가능 → bucketize 권장(예: 0-5s/5-30s/30s+)

## Non-goals
- OLAP 적재(=I-0305)
- 학습 라벨 생성(=B-0290)
- outbox relay(=B-0248)

## DoD
- BFF에서 search_impression/click/dwell outbox_event가 기록됨
- payload에 imp_id, position, query_hash, pipeline/experiment 정보가 포함됨
- dedup_key로 중복 방지 확인
- 샘플 로그로 “impression → click → dwell” 연결이 가능함을 검증

## Observability
- metrics:
  - search_impression_total, click_total, dwell_total
  - click_through_rate_proxy, avg_dwell_ms_proxy
- tracing:
  - request_id/trace_id로 SR/QS/RS/MIS까지 연결 가능(후속)

## Codex Prompt
Add search event emission for ranking/LTR:
- Define v1 schemas for search_impression/click/dwell including imp_id, positions, query_hash, pipeline and experiment metadata.
- Emit events via outbox_event from BFF (search response + client callbacks).
- Implement deterministic dedup_key rules.
- Provide smoke tests verifying the event chain (impression->click->dwell) is joinable.
