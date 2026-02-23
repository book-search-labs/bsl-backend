# B-0387 — Chat Intent Calibration + Confidence Reliability Model

## Priority
- P1

## Dependencies
- B-0359, B-0375, B-0383

## Goal
인텐트 분류 confidence를 보정(calibration)해 과신(과도한 자동실행)과 과소신뢰(불필요한 보류)를 줄인다.

## Scope
### 1) Calibration dataset
- 인텐트별 예측 confidence vs 실제 정확도 매핑 데이터 구축
- 도메인(주문/배송/환불/정책)별 분리 관리

### 2) Reliability model
- 온도보정/아이소토닉 등 confidence 보정 방식 적용
- 인텐트별 threshold 동적 정책 지원

### 3) Routing integration
- calibrated confidence 기준 tool 강제/clarification/handoff 분기
- low-confidence 반복 시 티켓 전환 우선

### 4) Monitoring loop
- calibration drift 감지
- 월간 재보정 주기 운영

## Observability
- `chat_intent_confidence_calibrated_total{intent}`
- `chat_intent_overconfidence_total{intent}`
- `chat_intent_underconfidence_total{intent}`
- `chat_intent_calibration_error{intent}`

## Test / Validation
- calibration 전후 Brier score/ECE 비교
- threshold 변경 회귀 테스트
- routing 분기 품질 테스트

## DoD
- 과신/과소신뢰로 인한 오분기 감소
- confidence 기반 분기 일관성 개선
- calibration drift를 운영에서 탐지 가능

## Codex Prompt
Improve intent confidence reliability:
- Calibrate intent probabilities and track calibration quality metrics.
- Route tool calls/clarifications using calibrated confidence thresholds.
- Detect calibration drift and refresh thresholds periodically.
