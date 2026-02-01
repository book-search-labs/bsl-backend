# B-0290 — LTR 학습 라벨 생성 잡(implicit labeling): click/dwell/cart/purchase → relevance label

## Goal
검색 로그(노출/클릭/체류/장바구니/구매)로부터 LTR 학습용 **implicit labels**를 생성한다.

- 입력: `search_impression`, `click`, `dwell`, (옵션) `add_to_cart`, `purchase`
- 출력: query-doc pair에 대한 label(0~4 등급) + 학습 피처 조인을 위한 키
- 핵심: position bias 최소 고려(기본 버전은 규칙 기반)

## Background
- 도서검색은 정답 라벨이 희소 → implicit feedback이 현실적
- “라벨 생성 품질”이 LTR 성공의 80%

## Scope
### 1) Input event assumptions
- impression:
  - imp_id, request_id, session_id, query_hash, results[{doc_id, position}]
- click:
  - imp_id, doc_id, position, ts
- dwell:
  - imp_id, doc_id, dwell_ms
- (옵션) cart/purchase:
  - session_id or user_id, doc_id, ts, order_id

### 2) Label rule (v1)
예시 0~4:
- purchase: 4
- add_to_cart: 3
- click + dwell_ms >= 30s: 2
- click (dwell 짧음): 1
- impression only: 0

### 3) Output dataset schema (OLAP table 권장)
- `ltr_training_example`:
  - date, query_hash, doc_id, label, position, imp_id
  - session_id(optional), user_id(optional)
  - policy/experiment tags
  - point-in-time join key(예: feature_snapshot_date)

### 4) Negative sampling (필수)
- 같은 impression 내에서:
  - clicked doc vs non-clicked docs를 함께 구성
- 상한:
  - query당 negatives max N (예: 50~200)

### 5) Data quality checks (필수)
- label 분포/결측률
- query당 example 개수 분포
- 이상치(dwell_ms 비정상) 제거

## Non-goals
- IPS/interleaving 구현(=B-0291)
- LTR 학습 파이프라인(=B-0294)

## DoD
- 최근 N일 데이터로 `ltr_training_example` 생성 성공
- 라벨 분포 리포트 출력 가능
- 재실행 멱등(동일 날짜 재생성 시 동일 결과)
- 최소 1k 쿼리/수십만 example까지 스케일 테스트

## Codex Prompt
Build implicit label generation job:
- Consume/search events in OLAP and generate ltr_training_example with labels 0-4 using click/dwell/cart/purchase rules.
- Include negative sampling from impressions and output partitioned tables by date.
- Add data-quality checks and make the job idempotent for reruns.
