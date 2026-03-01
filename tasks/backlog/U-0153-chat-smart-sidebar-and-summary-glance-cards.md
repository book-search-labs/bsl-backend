# U-0153 — Chat Smart Sidebar + Summary Glance Cards UX

## Priority
- P2

## Dependencies
- U-0150, U-0152
- B-0394

## Goal
책봇 사용 중 현재 맥락과 다음 행동을 사이드 요약 카드로 보여줘 사용자가 긴 대화를 읽지 않고도 즉시 진행 가능하게 한다.

## Scope
### 1) Summary glance cards
- 현재 목표(예: 주문 상태 확인) / 진행 단계 / 남은 입력값 표시
- 최근 확정 정보(주문번호, 배송 상태, 환불 가능 여부) 카드 노출
- 카드 클릭 시 해당 대화 turn로 점프

### 2) Smart sidebar behavior
- 데스크톱: 우측 고정 사이드바
- 모바일: 하단 드로어형 요약 패널
- 진행 상태 변화 시 최소 모션으로 업데이트

### 3) Action-first CTA
- 카드 내 "다음 단계 진행" CTA 제공
- 실패 상태면 재시도/티켓 전환 CTA 우선 노출

## DoD
- 긴 대화 탐색 시간 감소
- 요약 카드 기반 재진입 성공률 증가
- 모바일/데스크톱 레이아웃 안정성 확보

## Codex Prompt
Build smart chat summary UX:
- Show contextual glance cards for current goal, progress, and next action.
- Provide responsive sidebar/drawer behavior.
- Prioritize actionable CTAs for resume/retry/escalation.
