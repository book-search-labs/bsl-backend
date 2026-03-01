# B-0390 — Chat Answer Risk Banding + Tiered Approval Flow

## Priority
- P1

## Dependencies
- B-0383, B-0369, A-0148

## Goal
답변 위험도를 등급화해 고위험 답변은 추가 검증/승인 흐름을 거치게 만들어 오답/정책위반 리스크를 줄인다.

## Scope
### 1) Risk band model
- 답변을 `R0/R1/R2/R3` 등급으로 분류
- 기준: 인텐트 민감도, claim 수, 근거 신뢰도, 정책 충돌 여부

### 2) Tiered approval flow
- 저위험은 자동 응답
- 고위험은 추가검증/보수응답/운영승인 큐 전환

### 3) Response policy by band
- 밴드별 허용 표현/금지 표현/필수 문구 정의
- R3는 자동 실행 금지 및 상담 전환

### 4) Audit and feedback
- 밴드 결정 근거 저장
- 잘못된 밴드 분류 피드백 루프 구축

## Observability
- `chat_answer_risk_band_total{band}`
- `chat_answer_risk_escalation_total{band,action}`
- `chat_answer_risk_misband_total`
- `chat_answer_risk_approval_latency_ms`

## Test / Validation
- 밴드 분류 정확도 테스트
- 밴드별 정책 집행 회귀 테스트
- 승인 큐 전환/처리 흐름 테스트

## DoD
- 고위험 답변의 무검증 노출 감소
- 밴드별 응답 정책 일관성 확보
- 운영 승인 개입이 필요한 케이스를 선제 식별

## Codex Prompt
Introduce risk-banded response controls:
- Classify each answer by risk and enforce tiered handling policies.
- Escalate high-risk outputs to stricter validation or approval flows.
- Audit risk decisions and track misbanding feedback for improvement.
