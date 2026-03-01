# U-0145 — Chat Incident Recovery & User Guidance UX

## Priority
- P2

## Dependencies
- U-0144, I-0353, I-0354

## Goal
챗봇 장애/저하 상황에서 사용자가 현재 상태를 이해하고, 대체 경로(재시도/티켓/상담)로 빠르게 이동할 수 있는 UX를 제공한다.

## Scope
### 1) Incident-aware banners
- 지연/부분장애/제한모드 상태 배너 표시
- 영향 범위와 예상 복구시간(가능한 경우) 노출

### 2) Guided recovery actions
- 재시도, 문의 티켓 생성, 상담 전환 액션 버튼 제공
- 진행 중 workflow 복원 여부를 명확히 표시

### 3) Failure transparency
- 일반 오류 메시지 대신 reason_code 기반 사용자 메시지
- "무엇을 하면 해결되는지" 다음 행동 제시

### 4) UX consistency
- 모바일/데스크톱/접근성 일관성 확보

## DoD
- 장애 상황 이탈률 감소
- 실패 후 성공 전환(재시도/티켓) 비율 개선
- 사용자 불만(무반응/의미불명 오류) 감소

## Codex Prompt
Improve chat failure UX:
- Make incident states visible with clear impact and recovery guidance.
- Provide explicit next actions (retry, ticket, handoff) based on failure reason.
- Ensure consistent behavior across mobile/desktop accessibility contexts.
