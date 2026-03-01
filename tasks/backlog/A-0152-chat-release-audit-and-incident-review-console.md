# A-0152 — Chat Release Audit + Incident Review Console

## Priority
- P1

## Dependencies
- A-0150, A-0151
- I-0360, I-0361

## Goal
책봇 릴리스/장애 이력을 운영자가 감사 가능하게 관리하고, 사고 리뷰 결과를 다음 릴리스 승인에 자동 반영한다.

## Scope
### 1) Release audit timeline
- 릴리스 후보/승인/보류/롤백 이력 타임라인
- 변경된 모델/프롬프트/정책/게이트 결과 diff 제공
- 변경 책임자/승인자/사유 기록

### 2) Incident review workspace
- 장애 건별 원인/영향/조치/재발방지 항목 관리
- 장애와 관련된 지표/로그/티켓/런북 실행 이력 연결
- 리뷰 미완료 건은 다음 릴리스 승인 차단(옵션)

### 3) Governance feedback bridge
- 리뷰 결과를 backlog 개선 티켓으로 자동 생성
- 다음 릴리스 전 체크리스트 자동 생성

## DoD
- 릴리스와 장애 이력이 하나의 감사 뷰에서 추적 가능
- 사고 리뷰 결과가 실제 승인 프로세스에 반영
- 운영 감사 대응 자료를 즉시 export 가능

## Codex Prompt
Build a release-audit console for chat operations:
- Track release/rollback history with full diffs and accountability.
- Add incident review workspace linked to telemetry and runbooks.
- Feed review outcomes into release approval and backlog creation.
