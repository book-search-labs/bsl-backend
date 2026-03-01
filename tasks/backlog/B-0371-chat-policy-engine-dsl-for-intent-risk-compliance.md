# B-0371 — Chat Policy Engine DSL (Intent/Risk/Compliance)

## Priority
- P1

## Dependencies
- B-0364, B-0369, A-0144

## Goal
하드코딩 분기 대신 선언형 정책(DSL)으로 인텐트/리스크/컴플라이언스 규칙을 관리해 변경 속도와 일관성을 높인다.

## Non-goals
- 기존 커머스/권한 서비스의 실제 비즈니스 룰을 중복 구현하지 않는다.
- 정책 엔진에서 자유 텍스트 규칙 작성(비검증)은 허용하지 않는다.

## Scope
### 1) Policy DSL
- 조건: intent, user_tier, risk_level, reliability_level, locale
- 액션: allow, deny, ask_clarification, require_confirmation, handoff
- 우선순위, 유효기간, 실험 플래그 필드 포함

### 2) Runtime engine
- 요청마다 정책 평가 trace 생성
- 충돌 정책 우선순위/short-circuit 룰 정의

### 3) Versioning/rollback
- 정책 번들 버전 관리 + staged rollout
- 롤백 시 즉시 이전 버전 재적용

### 4) Safety checks
- 정책 lint/정합성 검사(모순 규칙 탐지)
- deny 정책 누락에 대한 위험 경고

## Data / Schema
- `chat_policy_bundle` (new): policy_version, status, checksum, created_by, approved_by, created_at
- `chat_policy_rule` (new): policy_version, priority, condition_json, action_json, enabled
- `chat_policy_eval_audit` (new): request_id, policy_version, matched_rule_ids, final_action, latency_ms
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Interfaces
- `POST /v1/chat` (정책평가 경유)
- `GET /internal/chat/policy/{version}` (운영 확인)
- `POST /internal/chat/policy/validate` (lint/정합성 검사)

## Observability
- `chat_policy_eval_total{policy_version,result}`
- `chat_policy_conflict_total{type}`
- `chat_policy_action_total{action}`
- `chat_policy_fallback_total{reason}`
- `chat_policy_eval_latency_ms{policy_version}`

## Test / Validation
- 정책 단위 테스트(positive/negative)
- 충돌/우선순위 회귀 테스트
- 정책 버전 교체/롤백 e2e 테스트
- kill-switch 정책 즉시 반영 smoke 테스트

## DoD
- 인텐트/리스크 정책 변경이 코드 배포 없이 가능
- 정책 평가 trace로 의사결정 재현 가능
- 위험 정책 누락/충돌을 사전 탐지 가능
- 정책 변경 승인/롤백 이력이 감사 가능

## Codex Prompt
Build a declarative chat policy engine:
- Introduce DSL rules for intent, risk, and compliance actions.
- Evaluate policy per request with deterministic trace output.
- Support versioned rollout/rollback and policy lint checks.
