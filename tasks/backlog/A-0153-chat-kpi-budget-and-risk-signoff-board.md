# A-0153 — Chat KPI/Budget/Risk Sign-off Board

## Priority
- P1

## Dependencies
- A-0150, A-0152
- B-0391, I-0360, I-0362

## Goal
운영/제품 책임자가 릴리스 전 KPI·비용·리스크를 한 번에 검토하고 sign-off 결정을 내릴 수 있는 보드를 제공한다.

## Scope
### 1) KPI sign-off panel
- completion rate, groundedness, insufficient-evidence rate, escalation rate 표시
- 목표 대비 편차를 색상/상태로 표기

### 2) Budget sign-off panel
- 토큰/툴콜/인프라 비용 예산 대비 소진률
- 예산 초과 원인 상위 세그먼트 분석

### 3) Risk sign-off panel
- 보안/정책/데이터 거버넌스 위반 현황
- 미해결 고위험 항목이 있으면 승인 차단

### 4) Decision audit
- 승인/보류/차단 사유 템플릿 저장
- 릴리스별 서명자/시각/근거 지표 스냅샷 보관

## DoD
- sign-off 결정이 단일 보드에서 완료됨
- KPI/예산/리스크 차단 조건 자동 적용
- 감사 추적 가능한 승인 이력 저장

## Codex Prompt
Create an admin sign-off board for chat releases:
- Combine KPI, budget, and risk gates in one decision workflow.
- Block approvals on unresolved high-risk conditions.
- Persist auditable decision evidence per release.
