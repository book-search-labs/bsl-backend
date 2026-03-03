# B-0375 — Chat Ticket Triage Classifier + SLA Estimator

## Priority
- P1

## Dependencies
- B-0370, B-0368, A-0145

## Goal
챗봇에서 생성되는 지원 티켓을 자동 분류/우선순위화하고 예상 처리시간(SLA)을 산정해 대응 속도와 정확도를 높인다.

## Non-goals
- 상담 인력 스케줄링 엔진 자체를 구현하지 않는다.
- 단일 모델 결과를 절대 기준으로 강제하지 않는다(운영 보정 허용).

## Scope
### 1) Triage taxonomy
- 카테고리: 주문/결제/배송/환불/계정/기타
- 심각도: `S1/S2/S3/S4` 분류 기준 정의

### 2) Classifier pipeline
- 챗 대화 요약 + reason_code + tool 실패정보를 입력으로 사용
- low-confidence 결과는 수동 검토 큐로 보냄

### 3) SLA estimation
- 카테고리/심각도/시간대 기반 예상 응답시간 추정
- SLA 초과 위험 케이스에 우선 알림

### 4) Feedback loop
- 실제 처리결과와 예측값 오차 추적
- 월별 재학습/룰 보정 사이클

## Data / Schema
- `chat_ticket_triage_prediction` (new): ticket_id, predicted_category, predicted_severity, confidence, model_version, created_at
- `chat_ticket_sla_estimate` (new): ticket_id, predicted_response_minutes, breach_risk_score, features_snapshot, created_at
- `chat_ticket_triage_feedback` (new): ticket_id, final_category, final_severity, corrected_by, corrected_at
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Interfaces
- `POST /internal/chat/tickets/triage/predict`
- `POST /internal/chat/tickets/sla/estimate`
- `POST /internal/chat/tickets/triage/feedback`

## Observability
- `chat_ticket_triage_total{category,severity}`
- `chat_ticket_triage_low_confidence_total`
- `chat_ticket_sla_prediction_error_minutes`
- `chat_ticket_sla_breach_risk_total`
- `chat_ticket_triage_feedback_applied_total`

## Test / Validation
- 분류 정확도/재현율 평가셋 검증
- low-confidence fallback 경로 테스트
- SLA 예측오차 모니터링 검증
- 모델/룰 버전 전환 시 회귀 테스트

## DoD
- 자동 분류 정확도 목표 달성
- 고위험 티켓 탐지율 개선
- SLA 예측값/실측값 비교 리포트 자동 생성
- 오분류 정정 피드백이 다음 버전에 반영되는 루프 확인

## Codex Prompt
Implement chat ticket triage intelligence:
- Classify category and severity from chat/ticket context.
- Estimate SLA risk and route low-confidence cases to manual review.
- Track prediction quality and close the loop with real outcomes.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Triage taxonomy gate 추가
  - `scripts/eval/chat_ticket_triage_taxonomy.py`
  - 카테고리/심각도 필수 집합, 중복, severity rule 누락을 게이트화
  - taxonomy version/staleness 검증 포함
  - gate 모드에서 taxonomy 품질 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_ticket_triage_taxonomy.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TICKET_TRIAGE_TAXONOMY=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Classifier pipeline gate 추가
  - `scripts/eval/chat_ticket_classifier_pipeline.py`
  - low-confidence 분류의 manual review 라우팅 커버리지 검증
  - unknown category/severity, model_version 누락, 입력 signal 누락을 게이트화
  - gate 모드에서 classifier 품질 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_ticket_classifier_pipeline.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TICKET_CLASSIFIER_PIPELINE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] SLA estimator gate 추가
  - `scripts/eval/chat_ticket_sla_estimator.py`
  - high-risk 티켓의 alert 누락 건수 및 estimator 근거 누락(features/model_version) 검증
  - 예측 오차(MAE)와 SLA breach recall을 게이트화
  - gate 모드에서 SLA estimator 품질 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_ticket_sla_estimator.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_TICKET_SLA_ESTIMATOR=1 ./scripts/test.sh`
