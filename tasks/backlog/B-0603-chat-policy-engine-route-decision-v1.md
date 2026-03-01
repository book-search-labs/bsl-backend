# B-0603 — Chat Policy Engine v1 (ASK/OPTIONS/CONFIRM/EXECUTE/ANSWER)

## Priority
- P0

## Dependencies
- B-0601
- B-0602
- B-0611

## Goal
intent/slot 해석과 라우팅 결정을 독립 모듈로 분리해 정책 일관성과 회귀 안정성을 확보한다.

## Why
- 현재 정책 판단이 분산되어 있어 동일 입력에 route drift가 발생하기 쉬움

## Scope
### 1) Structured understanding
- controller output: `intent`, `slots`, `standalone_query`, `risk_level`, `q_key`

### 2) Route decision
- `ASK` / `OPTIONS` / `CONFIRM` / `EXECUTE` / `ANSWER`
- missing slot 기반 질문 생성
- write-sensitive는 `CONFIRM` 선행 강제

### 3) Decision trace
- `reason_code`, `policy_rule_id`, `decision_snapshot` 저장

## DoD
- 동일 입력/상태에서 deterministic route를 반환한다.
- missing slot이 있으면 execute path를 차단한다.
- 모든 route가 reason_code와 함께 기록된다.

## Interfaces
- policy engine module (`decide_route(context)`)
- state patch contract

## Observability
- `chat_route_total{route,intent}`
- `chat_policy_block_total{reason_code}`

## Test / Validation
- intent-slot-route golden tests
- missing slot routing tests
- write confirm gate tests

## Codex Prompt
Extract a dedicated policy decision layer:
- Convert understanding output into explicit route decisions.
- Persist reason codes/rules per decision.
- Block execute on missing slots or missing confirmation.
