# B-0383 — Chat Output Contract Guard + Claim Verifier

## Priority
- P1

## Dependencies
- B-0353, B-0360, B-0371

## Goal
최종 답변이 형식/정책/사실 주장 규칙을 만족하는지 응답 직전에 검증해 위험한 출력이 사용자에게 전달되지 않도록 한다.

## Non-goals
- 생성 모델 자체 파인튜닝은 포함하지 않는다.
- 정책 원본 규칙 변경 기능은 본 티켓 범위가 아니다.

## Scope
### 1) Output contract checks
- 금지 문구/금지 액션/필수 필드 존재 여부 검증
- 금액/날짜/상태 문자열 형식 정합성 검증

### 2) Claim verifier
- 핵심 주장 문장을 citation evidence와 entailment 재검증
- 불일치 claim은 자동 제거 또는 abstain

### 3) Policy integration
- 정책 엔진 결과(allow/deny/clarify)와 답변 일관성 체크
- 불일치 시 응답 강등(reason_code 포함)

### 4) Failure handling
- guard 실패 시 한국어 fallback 템플릿 제공
- 운영 triage 큐로 자동 이벤트 적재

## Interfaces
- `POST /v1/chat` (final guard before response)
- `POST /internal/chat/output-guard/validate`
- `POST /internal/chat/claim-verifier/check`

## Data / Schema
- `chat_output_guard_audit` (new): request_id, guard_result, reason_codes, downgraded, latency_ms, created_at
- `chat_claim_verifier_audit` (new): request_id, claim_id, verdict, evidence_refs, created_at
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Observability
- `chat_output_guard_total{result,reason}`
- `chat_claim_verifier_mismatch_total`
- `chat_output_guard_downgrade_total{reason}`
- `chat_output_guard_latency_ms`
- `chat_output_guard_fallback_total{template}`

## Test / Validation
- 출력 계약 위반 케이스 단위 테스트
- claim mismatch 회귀 테스트
- guard 실패 fallback 일관성 테스트
- 정책 엔진 결과와 출력 불일치 차단 회귀 테스트

## DoD
- 정책/형식 위반 출력 사용자 노출 감소
- claim 불일치 답변의 자동 차단/강등 보장
- guard 결과가 운영 대시보드에서 추적 가능
- 고위험 인텐트에서 guard 미적용 누락 0건

## Codex Prompt
Add a final output guard for chat responses:
- Validate response contracts (format, policy, forbidden actions).
- Re-verify high-impact claims against citations before delivery.
- Downgrade or block unsafe outputs with deterministic Korean fallbacks.
