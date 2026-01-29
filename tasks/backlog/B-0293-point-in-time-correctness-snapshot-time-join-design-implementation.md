# B-0293 — Point-in-time correctness: 피처 스냅샷/타임조인(Offline/Online 일치)

## Goal
LTR 학습/평가에서 가장 흔한 실패 원인인 **offline/online feature mismatch**를 막기 위해  
“그 시점에 존재했던 피처값”으로 학습 데이터를 생성할 수 있도록 **point-in-time correctness**를 구현한다.

## Background
- 오늘의 CTR/popularity로 과거 클릭을 학습하면 누수(leakage) 발생
- 모델이 오프라인에선 좋아 보이는데 온라인에선 망하는 전형적인 원인

## Scope
### 1) Feature snapshotting (OLAP 권장)
- 일 단위 스냅샷 테이블:
  - `feat_doc_daily(date, doc_id, popularity_7d, ctr_doc, ...)`
  - `feat_qd_daily(date, query_hash, doc_id, ctr_qd, ...)`
- 집계 컨슈머(B-0292)가:
  - online KV에 최신값 쓰는 것과 별개로
  - 하루 1회(또는 배치)로 스냅샷을 OLAP에 적재

### 2) Training dataset time-join
- `ltr_training_example`(B-0290)에 `event_date` 또는 `feature_date` 포함
- join rule:
  - `feature_date = event_date` (또는 `event_date - 1` 안정적)
- SQL/파이프라인에서 time-join 강제

### 3) Feature spec single source
- `features.yaml`(B-0251)을 기준으로:
  - offline builder가 동일 변환/클리핑/기본값 적용

### 4) Validation
- offline vs online 샘플 비교 도구:
  - 동일 (query, doc)에 대해 온라인 KV vs 해당 date 스냅샷 비교
  - mismatch rate 리포트

## Non-goals
- 실시간 event-time 정확성(수분 단위)까지 완벽히
- 완전한 feature store 솔루션 도입(Feast 등)

## DoD
- 일 단위 피처 스냅샷이 생성된다
- 학습 데이터 생성 시 time-join이 강제된다
- offline/online mismatch 점검 리포트가 최소 1개 존재
- leakage 방지 규칙이 문서화된다

## Codex Prompt
Implement point-in-time correctness:
- Add daily feature snapshot tables in OLAP for doc and query-doc features.
- Ensure LTR training examples time-join to snapshots based on event_date (avoid leakage).
- Use features.yaml as the single source for transformations and provide a validation script to measure offline/online mismatch.
