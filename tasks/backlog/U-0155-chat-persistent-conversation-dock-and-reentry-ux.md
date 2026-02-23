# U-0155 — Chat Persistent Conversation Dock + Re-entry UX

## Priority
- P1

## Dependencies
- U-0150, U-0153, U-0154
- B-0396

## Goal
페이지 이동/새로고침/네트워크 변동 상황에서도 책봇 대화를 잃지 않고 즉시 재진입할 수 있는 고정 도크 UX를 제공한다.

## Scope
### 1) Persistent conversation dock
- 우측 하단 도크의 열림/닫힘/위치 상태를 세션 단위로 유지
- 페이지 이동 시 현재 대화 맥락과 미완료 액션 배지 유지
- 미읽음/미완료 단계 카운트 표시

### 2) Re-entry shortcuts
- "마지막 상담 이어하기" 단일 CTA 제공
- 최근 해결 플랜 1~3개를 요약 카드로 노출
- 카드 클릭 시 해당 단계로 즉시 점프

### 3) Failure-resume UX
- 연결 복구 후 누락된 메시지 재동기화 상태 표시
- 복구 실패 시 수동 재시도 + 상담 전환 버튼 노출
- 모바일에서는 하단 플로팅 버튼 + 시트 형태로 동일 기능 제공

### 4) Accessibility & consistency
- 키보드 탐색/스크린리더 레이블 완비
- 데스크톱/모바일 컴포넌트 상태 모델 통일
- route별 도크 숨김 예외 정책(결제 완료 등) 정의

## DoD
- 페이지 이동 중 대화 이탈률이 감소
- 재진입 CTA 클릭 후 복구 성공률이 운영 목표를 충족
- 모바일/데스크톱에서 동일한 핵심 플로우가 동작함

## Codex Prompt
Implement persistent chat re-entry UX:
- Keep widget state and unresolved actions across route transitions.
- Add one-click resume shortcuts for recent unresolved conversations.
- Provide robust resume UX for reconnect and sync-failure scenarios.
