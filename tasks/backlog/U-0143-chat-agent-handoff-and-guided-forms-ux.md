# U-0143 — Chat Agent Handoff + Guided Forms UX

## Priority
- P2

## Dependencies
- B-0359, U-0142

## Goal
챗봇이 해결하지 못하는 케이스에서 사람 상담/가이드 폼으로 자연스럽게 전환한다.

## Scope
### 1) Handoff trigger
- 반복 실패/고위험 질의/사용자 요청 시 handoff 제안

### 2) Guided form
- 주문번호, 문제 유형, 스크린샷 링크 등 최소 정보 폼
- 제출 후 접수번호 표시

### 3) Conversation continuity
- handoff 전 대화 요약을 상담 접수 데이터로 전달

## DoD
- handoff 후 이탈률 감소
- 상담 접수 정보 누락률 감소

## Codex Prompt
Implement chat handoff UX:
- Add handoff triggers and guided support form flows.
- Preserve conversation summary into support ticket payload.
- Show clear Korean status and ticket receipt UX.
