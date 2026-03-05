---
title: "18. 기술 부채와 리팩토링 우선순위"
slug: "bsl-backend-series-18-tech-debt-priority"
series: "BSL Backend Technical Series"
episode: 18
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 18. 기술 부채와 리팩토링 우선순위

## 지금까지 확보한 기술 자산
로컬 개발 기준에서 실제로 완성한 핵심은 아래 다섯 축입니다.

1. 계약 게이트
- `validate_contracts.py`, `contract_compat_check.py`

2. 검색 파이프라인 분리
- Query prepare/enhance
- Search hybrid/fallback
- Ranking 2-stage/mis cache

3. 모델 호출 경계 분리
- MIS, LLM Gateway

4. 트랜잭션 정합 구조
- Commerce 상태머신
- Outbox relay + replay

5. 데이터 피드백 루프
- OLAP 집계 -> 라벨링 -> 학습셋 -> parity 검증

## 기술적으로 큰 효과가 있던 선택
1. 상태/이유코드 중심 설계
- skip/fallback/degrade를 모두 reason code로 남겨 디버깅 속도 향상

2. 서비스 경계 분리
- Query/ Search/ Ranking/ MIS 역할이 분리되어 원인 분석 경로가 짧아짐

3. 재현 가능한 실패 복구
- reindex pause/resume/retry
- outbox replay
- chat replay artifact

## 남은 기술 부채 (우선순위)
### 1) `HybridSearchService` 분해
현재 클래스가 너무 많은 정책을 한 곳에서 처리합니다.

우선 분해 대상:
- enhance orchestration
- fallback planner
- rerank policy

분해 기준은 “기능별 테스트 가능 단위”입니다.

### 2) Query Enhance 정책 외부화
지금은 env + 코드 분기가 많습니다. reason->strategy 매핑을 선언형 설정으로 옮기면 실험 비용이 낮아집니다.

### 3) Chat Graph 계약 타입 강화
런타임 검증(`ChatGraphStateValidationError`)은 잘 동작하지만, 정적 타입 안전성은 아직 약합니다.

다음 단계:
- 노드 입출력 타입 생성
- replay 스키마 버전 고정

### 4) Outbox 멱등 보강
현재도 `dedup_key`를 쓰지만, consumer 관점 end-to-end exactly-once 검증 스크립트는 부족합니다.

### 5) Online/Offline feature 일치 자동화
`validate_feature_snapshot.py`는 단발 실행에 가깝습니다. 주기적 배치 + 리포트 누적 포맷을 추가하면 회귀 추적이 쉬워집니다.

## 다음 구현 순서 제안
1. SearchService 분해 + 단위 테스트 보강
2. Query Enhance 선언형 정책 테이블화
3. Chat Graph 타입/스키마 고정
4. Outbox consumer dedup 테스트 패키지 작성
5. Feature parity 리포트 자동 누적

이 시리즈의 결론은 단순합니다. “멋진 아키텍처 설명”보다, 로컬에서 반복 실행 가능한 기술 자산을 남기는 쪽이 장기적으로 훨씬 강합니다.

## 6) 남은 부채를 작업 단위로 쪼개기
기술 부채는 “리팩토링 필요” 수준으로 두지 않고 작업 단위로 나누는 것이 중요합니다.

### 6-1) `HybridSearchService` 분해
1. enhance orchestration 추출
2. fallback planner 추출
3. rerank policy 추출
4. 각 모듈 단위 테스트 작성

### 6-2) Query Enhance 정책 외부화
1. reason->strategy 매핑을 설정 파일로 분리
2. gate threshold를 환경별 프로파일로 분리
3. 정책 변경 diff를 테스트로 검증

### 6-3) Chat Graph 타입 강화
1. 노드 입출력 타입 스키마 고정
2. replay payload version 필드 강제
3. 상태 검증 실패 재현 fixture 추가

## 7) 품질 개선 효과를 측정하는 방법
리팩토링 이후에는 아래 지표를 같이 봐야 합니다.

1. reason code 분포 변화
2. fallback/degrade 비율 변화
3. cache hit/miss 변화
4. replay mismatch ratio 변화
5. 테스트 실행 시간 대비 실패 검출률

지표를 같이 보지 않으면 리팩토링 효과를 검증하기 어렵습니다.

## 8) 로컬 로드맵(실행 순서)
1. Search 분해 + 단위테스트
2. Query Enhance 정책 테이블화
3. Chat Graph 타입/스키마 고정
4. Outbox consumer dedup 검증 스크립트
5. Feature parity 리포트 자동 누적

이 순서는 코드 복잡도와 회귀 위험을 같이 줄이기 위한 우선순위입니다.

## 9) 마지막 정리
이 프로젝트에서 가장 큰 기술적 성과는 기능 수가 아니라 “반복 가능한 검증 구조”를 만든 점입니다.

1. 계약은 스키마/샘플/호환성 게이트로 검증합니다.
2. 검색/랭킹/챗은 reason code와 degrade 경로를 남깁니다.
3. 상태머신과 replay로 실패를 재현합니다.
4. OLAP 파이프라인으로 학습 데이터 정합성을 확인합니다.

이 원칙을 유지하면, 로컬 사이드프로젝트에서도 기술 복잡도를 통제하면서 기능을 확장할 수 있습니다.
