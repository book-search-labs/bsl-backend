# A-0146 — Chat Ticket Ops Quality + SLA Command Center

## Priority
- P2

## Dependencies
- A-0144, B-0375, B-0376

## Goal
운영자가 챗-연계 티켓의 분류 품질, SLA 위험, 처리 병목을 한 화면에서 관리할 수 있도록 운영 콘솔을 제공한다.

## Scope
### 1) Triage quality board
- 자동 분류 결과 vs 실제 카테고리/심각도 비교
- 오분류 상위 패턴/근본원인 표시

### 2) SLA risk board
- SLA breach 위험 티켓 우선 큐
- 에스컬레이션/재배정 액션 제공

### 3) Evidence quality checks
- evidence pack 완전성 점수 표시
- 누락 필드/마스킹 오류 탐지

### 4) Ops reporting
- 주간 SLA 리포트/오분류 리포트 export
- 개선 액션 티켓 자동 생성(옵션)

## DoD
- 운영자가 SLA 위험 케이스를 신속히 식별
- 자동 분류 품질 개선 루프가 정착
- 티켓 처리 병목 지점의 가시성 향상

## Codex Prompt
Build an operations command center for chat-driven tickets:
- Monitor triage quality, SLA risk, and evidence completeness.
- Enable fast escalation/reassignment actions.
- Provide exportable reports and feedback loops for quality improvement.
