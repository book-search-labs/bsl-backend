# B-0715 — Reason Code Taxonomy Governance Gate

## Priority
- P1

## Dependencies
- B-0703
- B-0609

## Goal
리라이트 이후 reason_code 일관성을 유지하기 위해 taxonomy 정책과 게이트를 중앙화한다.

## Scope
### 1) Taxonomy policy
- 허용 패턴 정의: `^[A-Z][A-Z0-9_]*(:[A-Z0-9_]+)*$`
- 금지 코드: `UNKNOWN`, `NO_REASON` 등 모호 코드
- lane별 접두 정책(`ROUTE:`, `TOOL_FAIL:`, `DENY_EXECUTE:`) 표준화

### 2) Runtime metrics
- `chat_reason_code_total{source,reason_code}` 집계
- invalid/unknown 비율 계산 및 대시보드 노출

### 3) Eval gate
- reason_code taxonomy eval 스크립트 운영
- baseline 대비 악화 회귀 감지(unknown 증가, invalid ratio 증가)

### 4) Regression enforcement
- fixture expected reason_code 패턴 검증
- 실제 응답 reason_code 패턴 검증

## Test / Validation
- taxonomy lint tests
- reason_code eval script tests
- regression harness reason_code validation tests

## DoD
- invalid reason_code 비율이 0%를 유지한다.
- unknown reason_code 예산을 초과하면 gate에서 차단된다.
- reason_code drift가 CI에서 즉시 감지된다.

## Codex Prompt
Govern reason-code taxonomy for rewritten chat engine:
- Define strict reason-code policy and disallow ambiguous codes.
- Add runtime metrics + eval gate for invalid/unknown rates.
- Enforce taxonomy in fixtures and live response regression tests.
