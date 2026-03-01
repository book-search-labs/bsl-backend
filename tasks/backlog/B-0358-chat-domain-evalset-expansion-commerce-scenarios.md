# B-0358 — 도메인 평가셋 확장 (도서검색/주문/환불/배송/이벤트 안내)

## Goal
실제 사용자 질문 분포를 반영한 챗봇 평가셋을 구축해 품질 측정을 현실화한다.

## Why
- 범용 QA 데이터만으로는 현재 서비스 품질을 제대로 반영하지 못함
- 커머스/운영 시나리오를 포함해야 실전 품질을 보장할 수 있음

## Scope
### 1) 시나리오 축
- 도서 검색/추천
- 장바구니/주문/결제
- 배송/환불/반품 정책
- 이벤트/공지 안내

### 2) 라벨 구조
- expected answer intent
- required citations
- abstain expected 여부
- 금지 답변 패턴

### 3) 버전 관리
- eval set 버전 태깅
- 변경 이력과 기준선 기록

### 4) 리포트 자동화
- 주기 실행(예: nightly)
- 실패 케이스 상위 N개 추출

## DoD
- 도메인 평가셋 v1 생성 및 버전 관리
- nightly 리포트 자동 생성
- 상위 실패 케이스가 개선 백로그와 연결

## Codex Prompt
Create domain-specific chat evaluation set:
- Cover search/commerce/shipping/refund/event scenarios.
- Define labels for expected intent, citations, and abstain behavior.
- Version datasets and generate scheduled failure reports.
