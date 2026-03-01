# A-0141 — Prompt/Policy 버전 운영 UI (승인/롤백/감사 로그)

## Goal
챗봇 프롬프트/정책 변경을 운영 UI에서 안전하게 관리한다.

## Why
- 수동 변경은 회귀/사고 발생 시 추적과 복구가 어려움

## Scope
### 1) 버전 관리
- prompt/policy 버전 생성/비교/배포
- active/canary 상태 표시

### 2) 승인 플로우
- 변경 요청 → 승인 → 배포
- 권한 기반 접근 제어

### 3) 롤백
- 원클릭 롤백 + 영향 범위 표시

### 4) 감사 로그
- 변경자/시각/변경 diff 저장

## DoD
- 정책 변경 이력이 100% 추적 가능
- 롤백 후 즉시 반영 검증 가능

## Codex Prompt
Implement prompt/policy ops UI:
- Add versioning, approval workflow, rollback, and audit logging.
- Support active/canary switch with safe rollback.
