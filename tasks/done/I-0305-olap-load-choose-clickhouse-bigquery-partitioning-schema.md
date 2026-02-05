# I-0305 — OLAP 적재(ClickHouse/BigQuery 택1) + 스키마/파티션

## Goal
검색/자동완성/챗/커머스 이벤트를 OLAP에 적재해
**집계(CTR/Popularity), LTR 학습 데이터, 오프라인 평가**의 기반을 만든다.

## Why
- LTR/추천/품질 평가가 “로그 기반”으로만 가능
- Kafka에만 있으면 분석/백필/회귀가 힘듦 → OLAP 필요

## Scope
### 1) 저장소 선택(v1)
- 로컬/스테이징: **ClickHouse** 추천(구축 쉬움, 성능 좋음)
- prod 대체: BigQuery(선택)

### 2) 이벤트 스키마(v1)
기본 테이블(파티션/정렬 포함):
- `search_impression` (분모)
- `click`
- `dwell`
- `ac_impression`
- `ac_select`
- (선택) `chat_turn`, `chat_feedback`
- (선택) `order_event` (커머스)

필수 컬럼 예:
- `event_time`, `event_type`
- `request_id`, `trace_id`, `session_id`, `user_id_hash`
- `query_hash`, `q_norm`(선택: 개인정보 이슈 고려)
- `imp_id`, `doc_id`, `position`
- `policy_id`, `experiment_id`, `variant`

### 3) 적재 방식
- v1: Kafka consumer → ClickHouse insert(배치/버퍼)
- v2: Kafka Connect/CDC(선택)

### 4) 파티션/TTL
- 파티션: day(event_time)
- TTL: 90~180일(프로젝트 규모 기준)
- dedup: `dedup_key` 기반 upsert/replace 전략(엔진 선택에 따라)

### 5) 데이터 품질 체크(간단)
- late arrival 허용 범위
- 이벤트 유실/중복 감지 지표(카운트 비교)

## Non-goals
- 완전한 데이터 레이크/카탈로그/라인리지(추후)
- BI 고도화(메타베이스는 I-0306)

## DoD
- ClickHouse(or BigQuery)에 핵심 이벤트 테이블 생성
- Kafka→OLAP 적재가 지속 동작(지연/에러 모니터링 포함)
- 파티션/TTL/중복 방지 전략 문서화
- LTR용 쿼리(예: label 생성용 join)가 가능

## Codex Prompt
Add OLAP storage & ingestion:
- Stand up ClickHouse (preferred) and create event schemas with partitions/TTL.
- Implement Kafka consumer ingestion with buffering and dedup strategy.
- Document schema, retention, and example analytical queries for LTR/eval.
- Validate by producing sample events and confirming OLAP counts match.
