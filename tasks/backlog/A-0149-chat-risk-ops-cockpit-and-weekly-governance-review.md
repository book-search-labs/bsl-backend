# A-0149 — Chat Risk Ops Cockpit + Weekly Governance Review

## Priority
- P2

## Dependencies
- A-0148, A-0147, B-0390

## Goal
운영자가 주간 단위로 챗봇 위험지표/승인개입/위반추세를 점검하고 개선 액션을 추적하는 관리 체계를 구축한다.

## Scope
### 1) Risk cockpit
- 위험밴드 분포, 고위험 전환율, 승인 큐 체류시간 지표
- 도메인/인텐트별 drill-down 제공

### 2) Weekly governance workflow
- 주간 리뷰 템플릿(핵심 이슈/원인/조치/담당자)
- 리뷰 결과를 후속 티켓으로 자동 연결(옵션)

### 3) Action tracking
- 위험완화 액션 상태(대기/진행/완료) 추적
- 미해결 고위험 항목 경고

### 4) Audit trail
- 리뷰 참석자/결정사항/근거 데이터 보존
- export/report 지원

## DoD
- 주간 거버넌스 리뷰 루틴 정착
- 고위험 이슈 대응 리드타임 단축
- 개선 액션 추적 누락 감소

## Codex Prompt
Create an operations cockpit for chat risk governance:
- Monitor risk-band metrics and approval queue health.
- Run weekly governance reviews with tracked action items.
- Preserve auditable decision history and exportable reports.
