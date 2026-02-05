# U-0116 — Web User: 장바구니 UI/UX (Cart)

## Goal
사용자가 상품을 장바구니에 담고 관리할 수 있게 한다.

## Why
- 커머스 플로우의 시작점
- 가격/재고 스냅샷 정책과 맞물려 운영 이슈가 자주 발생 → UI에서 명확히 보여줘야 함

## Scope
### 1) 장바구니 목록 화면
- 아이템 리스트: 표지/제목/수량/가격/합계
- 수량 변경(+/-) 및 직접 입력
- 삭제(아이템 단위), 전체 비우기

### 2) 가격/재고 경고 표시
- “가격이 변경되었음” 배지
- “재고 부족/품절” 배지 + 수량 자동 조정 안내

### 3) 합계/결제 버튼
- 총 상품금액/배송비/할인(있다면)
- CTA: “주문하기(Checkout)”

### 4) Empty state
- 빈 장바구니 안내 + 인기/추천(옵션) 또는 검색으로 유도

## Non-goals
- 쿠폰/포인트/프로모션은 후속 티켓

## DoD
- 장바구니 조회/수정/삭제가 UI에서 완결
- 가격/재고 변경이 사용자에게 명확히 노출
- Checkout으로 정상 이동

## Interfaces
- `GET /cart`
- `POST /cart/items`
- `PATCH /cart/items/{id}`
- `DELETE /cart/items/{id}`

## Files (예시)
- `web-user/src/pages/cart/CartPage.tsx`
- `web-user/src/components/cart/CartItemRow.tsx`
- `web-user/src/api/cart.ts`

## Codex Prompt
Build Cart UI:
- Implement Cart page with list, quantity updates, remove, clear.
- Show price/stock change warnings.
- Add summary panel and proceed-to-checkout CTA.
