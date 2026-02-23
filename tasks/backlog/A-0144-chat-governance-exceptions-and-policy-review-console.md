# A-0144 — Chat Governance Console (예외/정책 검토)

## Priority
- P2

## Dependencies
- A-0141, A-0142, B-0368

## Goal
운영자가 차단/예외/정책 충돌 케이스를 빠르게 검토하고, 승인/반려/룰수정 결정을 감사 가능하게 관리한다.

## Scope
### 1) Exception queue
- 차단된 프롬프트/민감 액션 거부/저신뢰 응답 사례 큐잉
- severity, domain, intent 기준 필터

### 2) Policy review workflow
- allowlist/denylist/threshold 조정 제안
- 2인 승인(옵션) 및 즉시 롤백

### 3) Evidence bundle
- 원문 질의, reason_code, 사용된 source trust 정보, 적용 정책 버전 표시
- 재현(replay) 링크 및 영향도 추정

### 4) Audit/export
- 변경 이력 및 승인 로그 저장
- 점검 리포트(export) 지원

## DoD
- 운영자가 예외 케이스를 1개 화면에서 triage 가능
- 정책 변경/롤백 이력 100% 추적 가능
- 고위험 정책 변경에 대한 승인 누락 0건

## Codex Prompt
Build a chat governance review console:
- Triage blocked/exception cases with policy and evidence context.
- Support approval workflows, rapid rollback, and complete audit logs.
- Provide replay links and change impact visibility for operators.
