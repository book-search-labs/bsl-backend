# B-0376 — Chat Case Evidence Pack Generator (Ticket Resolution)

## Priority
- P2

## Dependencies
- B-0370, B-0363, B-0371

## Goal
티켓 처리자가 바로 이해할 수 있도록 챗 세션의 핵심 맥락/근거/실패원인을 구조화한 증거 패키지를 자동 생성한다.

## Scope
### 1) Evidence pack schema
- 필수 항목: 대화 요약, 사용자 의도, 실행된 tool, 오류코드, 관련 주문/배송 ID
- 개인정보 최소화/마스킹 규칙 포함

### 2) Automatic assembly
- 세션 종료/티켓 생성 시 evidence pack 자동 생성
- 누락 필드 감지 시 보완 질문 가이드 생성

### 3) Resolution assistance
- 유사 과거 케이스/해결 템플릿 추천(옵션)
- 처리자가 추가 질문해야 할 항목 제안

### 4) Integrity checks
- 근거 링크 무효/누락 감지
- policy_version/tool_version 함께 기록

## Observability
- `chat_evidence_pack_created_total`
- `chat_evidence_pack_missing_field_total{field}`
- `chat_evidence_pack_redaction_applied_total`
- `chat_evidence_pack_resolution_time_minutes`

## Test / Validation
- 증거 패키지 필드 완전성 테스트
- PII 마스킹 회귀 테스트
- 누락정보 보완 흐름 테스트

## DoD
- 티켓당 초기 파악 시간 단축
- 증거 누락으로 인한 재문의 비율 감소
- 감사 시 evidence pack 재현 가능

## Codex Prompt
Generate structured chat evidence packs for support tickets:
- Build a schema with summary, intent, tools, errors, and references.
- Auto-assemble packs on ticket creation with redaction and integrity checks.
- Improve resolution speed with complete, reproducible context.
