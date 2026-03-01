# U-0146 — Chat Ticket Lifecycle Timeline + Escalation UX

## Priority
- P2

## Dependencies
- B-0370, B-0375, U-0143

## Goal
사용자가 챗 내에서 문의 티켓 상태를 단계별로 확인하고 필요 시 즉시 에스컬레이션할 수 있도록 UX를 제공한다.

## Scope
### 1) Ticket timeline view
- 상태 단계(`접수/처리중/추가정보요청/해결/종료`) 시각화
- 최근 업데이트 시각, 담당 상태, 다음 예상 단계 표시

### 2) Escalation actions
- SLA 초과 위험 시 "우선 처리 요청" 액션 제공
- 추가 정보 업로드/재문의 버튼 제공

### 3) Notification UX
- 상태 변경 시 챗 내 알림 배지/요약 메시지
- 미응답 경고 및 후속 안내

### 4) Clarity/accessibility
- 용어 단순화(한국어) + 모바일 접근성 보강

## DoD
- 티켓 상태 문의 반복 질의 감소
- 에스컬레이션 경로 사용성 개선
- 티켓 진행상황 이해도 향상

## Codex Prompt
Improve ticket lifecycle UX in chat:
- Show a clear status timeline with next-step guidance.
- Add escalation and additional-info actions when SLA risk increases.
- Keep the flow concise, Korean-first, and mobile-accessible.
