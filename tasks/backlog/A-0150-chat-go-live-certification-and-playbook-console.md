# A-0150 — Chat Go-Live 인증 콘솔 (품질 승인 + 운영 플레이북)

## Priority
- P1

## Dependencies
- A-0140, A-0142, A-0146, A-0149
- B-0391, I-0360

## Goal
운영자가 책봇 릴리스 전/후에 품질 인증, 리스크 점검, 롤백 의사결정을 한 화면에서 수행하도록 Admin 콘솔을 제공한다.

## Scope
### 1) Go-live certification board
- 릴리스 후보별 품질/안전/비용/SLA 지표 카드
- 컷라인 충족 여부와 차단 사유(reason_code) 표시
- 승인/보류/롤백 결정을 감사로그와 함께 기록

### 2) Playbook execution panel
- 장애 유형별 표준 대응 플로우(runbook step) 실행 UI
- LLM 장애, tool 장애, 근거 부족 급증, 비용 급증 시나리오 지원
- 실행 이력/조치 결과/후속 티켓 자동 링크

### 3) Governance snapshot
- 프롬프트/정책/모델 버전 조합의 변경 diff 시각화
- 고위험 변경 항목 하이라이트 및 2인 승인(옵션)

## DoD
- 운영자가 go-live 판단을 단일 콘솔에서 수행 가능
- 사고 대응 플레이북 실행률/완료율 측정 가능
- 승인/롤백 의사결정이 감사 가능 형태로 남음

## Codex Prompt
Build an admin go-live console for chat:
- Certify release candidates against hard launch gates.
- Provide runbook execution workflows for major incident classes.
- Track approval/hold/rollback decisions with full auditability.
