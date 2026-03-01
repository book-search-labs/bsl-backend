# B-0393 — Chat Grounded Answer Composer + Korean Policy Template Bundle

## Priority
- P1

## Dependencies
- B-0353, B-0360, B-0383, B-0391

## Goal
책봇 응답을 "근거 기반 + 한국어 정책 템플릿"으로 일관화하여, 실서비스에서 문체/정책 오차를 줄이고 신뢰 가능한 답변만 노출한다.

## Scope
### 1) Grounded answer composer
- retrieval/tool evidence를 claim 단위로 정렬해 답변 본문 생성
- claim마다 근거 스니펫/출처/시각 정보 연결
- 근거 미연결 claim은 본문 반영 금지

### 2) Korean policy template bundle
- 배송/환불/반품/주문 상태용 한국어 템플릿 세트 버전 관리
- reason_code별 템플릿 라우팅
- 날짜/금액/수수료/상태는 슬롯 주입으로만 출력

### 3) Output safety envelope
- 금칙 문구/법적 리스크 표현 필터
- 정책 불확실 시 단정 금지 + 안전 안내로 다운그레이드
- 템플릿 누락 시 fail-closed

## DoD
- 동일 reason_code에서 응답 톤/구조 일관성 확보
- 근거 누락 claim이 0%로 유지
- 템플릿 버전 변경 이력 추적 가능

## Codex Prompt
Implement a grounded answer composer:
- Build claim-level evidence binding for chat responses.
- Route Korean policy templates by reason_code.
- Block unsupported claims and enforce fail-closed output behavior.
