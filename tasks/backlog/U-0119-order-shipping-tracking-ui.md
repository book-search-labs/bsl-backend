# U-0119 — Web User: 주문내역/배송조회 UI

## Goal
사용자가 주문 상태를 확인하고(결제/출고/배송), 배송 추적을 할 수 있게 한다.

## Why
- 커머스 운영에서 CS의 1순위는 “내 주문 지금 어디임?”
- 주문/배송 상태가 명확하면 문의/이슈가 크게 줄어듦

## Scope
### 1) 주문 목록 (Order History)
- 기간 필터(최근 1/3/6개월), 상태 필터(optional)
- 주문 카드: 주문번호, 주문일, 총액, 상태(배지), 대표 상품 1~2개
- 페이징/무한스크롤 중 택1

### 2) 주문 상세
- 주문 기본정보: 주문번호/일시/수령인/배송지/연락처(마스킹)
- 아이템 리스트: 상품정보/수량/가격/합계
- 결제 정보: 결제수단/승인상태/영수증 링크(옵션)
- 주문 상태 타임라인:
  - CREATED → PAID → READY → SHIPPED → DELIVERED
  - 각 상태별 timestamp 표시

### 3) 배송조회 (Tracking)
- 송장번호/택배사/배송상태
- 외부 추적 URL 링크(옵션)
- 배송 이벤트 타임라인(있으면)

### 4) 액션(조건부 노출)
- 배송 전: “주문 취소”(U-0120과 연동)
- 배송 후: “환불/반품 신청”(추후 확장)

## Non-goals
- 반품 수거 예약/교환 등 복잡 플로우(후속 티켓)

## DoD
- 주문 목록/상세/배송조회가 UX로 완결
- 상태 타임라인이 서버 상태와 일치
- 오류/빈 상태(주문 없음) 처리 완료

## Interfaces
- `GET /orders?cursor=...`
- `GET /orders/{order_id}`
- `GET /shipments/by-order/{order_id}` 또는 `GET /shipments/{shipment_id}`
- `GET /tracking/{carrier}/{tracking_no}` (옵션)

## Files (예시)
- `web-user/src/pages/orders/OrderListPage.tsx`
- `web-user/src/pages/orders/OrderDetailPage.tsx`
- `web-user/src/components/orders/OrderStatusTimeline.tsx`
- `web-user/src/api/orders.ts`

## Codex Prompt
Implement Order history UI:
- List and detail pages with status timeline and tracking section.
- Conditional actions (cancel/refund entry points).
- Handle empty/error states and pagination.
