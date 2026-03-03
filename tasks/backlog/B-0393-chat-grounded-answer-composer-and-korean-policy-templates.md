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

## Implementation Update (2026-03-04, Bundle 1)
- [x] Grounded answer composer guard gate 추가
  - `scripts/eval/chat_grounded_answer_composer_guard.py`
  - claim binding coverage 및 response-level ungrounded claim 탐지 검증
  - ungrounded claim 출력 노출(unsupported claim exposure) 건수 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_grounded_answer_composer_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_GROUNDED_ANSWER_COMPOSER_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 2)
- [x] Korean policy template routing guard gate 추가
  - `scripts/eval/chat_korean_policy_template_routing_guard.py`
  - reason_code 기반 template routing coverage 및 wrong template 검증
  - required slots 주입 누락 및 non-korean template 위반 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_korean_policy_template_routing_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_KOREAN_POLICY_TEMPLATE_ROUTING_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 3)
- [x] Policy uncertainty safe fallback guard gate 추가
  - `scripts/eval/chat_policy_uncertainty_safe_fallback_guard.py`
  - 정책 불확실 구간의 단정 문구(unsafe definitive) 검증
  - 안전 안내 누락 및 fallback downgrade 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_policy_uncertainty_safe_fallback_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_POLICY_UNCERTAINTY_SAFE_FALLBACK_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 4)
- [x] Template missing fail-closed guard gate 추가
  - `scripts/eval/chat_template_missing_fail_closed_guard.py`
  - template missing 구간 fail-open 위반/unsafe rendered 검증
  - template missing reason_code 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_template_missing_fail_closed_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TEMPLATE_MISSING_FAIL_CLOSED_GUARD=1 ./scripts/test.sh`
