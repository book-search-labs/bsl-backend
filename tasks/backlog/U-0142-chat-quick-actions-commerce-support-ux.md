# U-0142 — Chat Quick Actions (주문/배송/환불/이벤트)

## Priority
- P2

## Dependencies
- B-0359

## Goal
사용자가 챗에서 자주 묻는 업무를 버튼형 빠른 액션으로 처리해 입력 부담과 실패를 줄인다.

## Scope
### 1) Quick action buttons
- "주문 조회", "배송 상태", "환불 규정", "이벤트 안내"

### 2) 컨텍스트 입력 도우미
- 주문번호 자동완성
- 최근 주문 선택

### 3) 실패 UX
- 액션 실패 시 복구 경로(재시도/고객센터)

## DoD
- quick action 경로의 완료율 개선
- 오류 시 사용자 이탈률 감소

## Codex Prompt
Implement chat quick actions:
- Add button-driven flows for order/shipping/refund/event support.
- Provide contextual selectors (recent orders/autocomplete).
- Add clear recovery UI for failures.
