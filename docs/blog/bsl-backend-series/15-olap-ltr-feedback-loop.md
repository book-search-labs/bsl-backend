---
title: "15. OLAP 피처 집계와 LTR 학습 데이터 구축"
slug: "bsl-backend-series-15-olap-ltr-feedback-loop"
series: "BSL Backend Technical Series"
episode: 15
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 15. OLAP 피처 집계와 LTR 학습 데이터 구축

## 핵심 목표
온라인 이벤트를 바로 학습에 쓰지 않고, OLAP에서 집계/라벨링/시점 정합 조인을 거친 뒤 학습셋으로 만듭니다.

핵심 파일:
- `infra/clickhouse/init.sql`
- `scripts/olap/aggregate_features.py`
- `scripts/olap/generate_ltr_labels.py`
- `scripts/olap/build_training_dataset.py`
- `scripts/olap/validate_feature_snapshot.py`

## 1) OLAP 테이블 구조
`init.sql` 기준 주요 테이블:
- 행동 이벤트: `search_impression`, `search_click`, `search_dwell`, `add_to_cart`, `purchase`
- 피처 집계: `feat_doc_daily`, `feat_qd_daily`
- 학습 라벨: `ltr_training_example`

중요 컬럼:
- `feature_snapshot_date`
- `experiment_id`, `experiment_bucket`

TTL도 테이블별로 다르게 설정해 보관 주기를 제어합니다.

## 2) 피처 집계 (`aggregate_features.py`)
집계는 단순 count가 아니라 decay를 사용합니다.

예시 계산:
- `sum(exp(-lambda * dateDiff(day, event_date, as_of)) * count)`

이 방식으로 최근 행동에 더 큰 가중치를 줍니다.

## 3) 라벨 생성 (`generate_ltr_labels.py`)
impression 기준으로 click/dwell/cart/purchase를 합쳐 라벨을 만듭니다.

핵심 규칙:
1. 행동 강도에 따른 label 부여
2. `max_negatives`로 negative 샘플 상한
3. 필요 시 `experiment_bucket` 필터

즉, 양성 샘플 부족/음성 샘플 과다를 스크립트 옵션으로 조절합니다.

## 4) 학습셋 빌드 (`build_training_dataset.py`)
point-in-time join이 핵심입니다.

- `t.feature_snapshot_date = f.event_date` (doc feature)
- `t.feature_snapshot_date = q.event_date` (query-doc feature)

미래 정보가 섞이지 않도록 날짜 축을 엄격히 맞춥니다.

## 5) 스냅샷 검증 (`validate_feature_snapshot.py`)
online feature와 offline snapshot 차이를 tolerance로 검증합니다.

- 기본 `--tolerance 0.02`
- delta 초과 시 실패

이 검증이 없으면 학습 성능은 올라가도 온라인 추론과 불일치가 커집니다.

## 로컬 실행 예시
```bash
python scripts/olap/aggregate_features.py --as-of 2026-03-01
python scripts/olap/generate_ltr_labels.py --start 2026-02-01 --end 2026-02-28
python scripts/olap/build_training_dataset.py --start 2026-02-01 --end 2026-02-28
python scripts/olap/validate_feature_snapshot.py --snapshot-date 2026-03-01
```

## 6) `init.sql` 기준 테이블 설계 포인트
1. 온라인 이벤트 테이블과 집계 테이블을 분리합니다.
2. `event_date` 기준 파티셔닝/정렬로 조회 효율을 확보합니다.
3. TTL을 이벤트 성격별로 다르게 둡니다(180일/365일 등).
4. 학습 예제(`ltr_training_example`)에 `feature_snapshot_date`를 저장합니다.

이 구조가 point-in-time 학습의 기반입니다.

## 7) 피처 집계 수식 해석
`aggregate_features.py`는 지수 감쇠를 사용합니다.

- `exp(-lambda * dateDiff(day, event_date, as_of))`

최근 이벤트에 높은 가중치를 주고, 과거 이벤트 영향은 점진적으로 줄입니다.

## 8) 라벨 생성 로직 상세
`generate_ltr_labels.py`에서 중요한 부분:

1. impression을 모수로 사용
2. 클릭/체류/장바구니/구매 신호를 단계적 label로 변환
3. 음성 샘플을 `max_negatives`로 제한
4. 필요 시 `experiment_bucket` 필터 적용

즉, 데이터 불균형을 제어하면서 학습 라벨을 만듭니다.

## 9) 학습셋 조인 안정성
`build_training_dataset.py`는 미래 누수를 막기 위해 snapshot date를 기준으로 조인합니다.

1. doc feature: `feature_snapshot_date = feat_doc_daily.event_date`
2. query-doc feature: `feature_snapshot_date = feat_qd_daily.event_date`

이 조건이 없으면 offline 성능이 과대평가됩니다.

## 10) parity 검증 로컬 팁
`validate_feature_snapshot.py`는 tolerance 초과 시 실패합니다.

추천 절차:
1. tolerance를 작은 값으로 유지(`0.02` 기본)
2. 초과 항목은 feature별 delta를 저장
3. 추후 모델 학습 전 parity 리포트를 먼저 확인

로컬에서도 이 단계를 습관화하면 학습-서빙 불일치를 줄일 수 있습니다.
