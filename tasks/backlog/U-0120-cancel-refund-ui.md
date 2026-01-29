# U-0120 — Web User: 취소/환불 UI (Cancel/Refund Request)

## Goal
사용자가 주문 취소/환불(부분환불 포함)을 신청할 수 있게 한다.

## Why
- 결제/재고/주문 상태 불일치의 핵심 구간
- UI에서 “가능 조건”을 명확히 보여줘야 운영사고가 줄어듦

## Scope
### 1) 취소 가능 조건 표시
- 주문 상태 기반:
  - 배송 전(CREATED/PAID/READY): 취소 가능
  - 배송 후(SHIPPED/DELIVERED): 환불/반품(정책에 따라)
- 아이템 단위 가능/불가 표시(부분취소/부분환불 지원 시)

### 2) 취소/환불 신청 폼
- 사유 선택(드롭다운) + 상세 사유(텍스트)
- 환불 방식 안내(결제수단으로 환불 등)
- 부분환불 시: 아이템 선택 + 수량 선택

### 3) 신청 결과/상태
- 신청 완료 화면 + 처리중 상태 표시
- 주문 상세에서 refund status 표시(REQUESTED/APPROVED/REJECTED/COMPLETED)

### 4) 안전장치 UX
- “취소 시 재고/결제 처리” 안내 문구
- 중복 제출 방지(버튼 disable, idempotency key는 서버가 담당)

## Non-goals
- 반품 수거/교환 프로세스 자동화(후속)

## DoD
- 취소/환불 신청이 성공적으로 생성되고 상태가 화면에 반영됨
- 불가능한 상태에서는 UI에서 신청이 차단되고 이유가 표시됨
- 재시도/오류 처리 완료

## Interfaces
- `POST /orders/{order_id}/cancel`
- `POST /refunds` (부분환불 포함)
- `GET /refunds/by-order/{order_id}`

## Files (예시)
- `web-user/src/pages/refund/RefundRequestPage.tsx`
- `web-user/src/components/refund/RefundItemSelector.tsx`
- `web-user/src/api/refund.ts`

## Codex Prompt
Implement Cancel/Refund UI:
- Gate by order status, support partial selection, capture reasons.
- Show request status in order detail and handle retries/errors.
