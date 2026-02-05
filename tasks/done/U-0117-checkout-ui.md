# U-0117 — Web User: Checkout UI (주소/배송/결제수단 선택)

## Goal
장바구니에서 주문 생성 전 단계(Checkout)를 완성한다.

## Why
- 주문 생성/결제 연동 전에 사용자가 입력해야 하는 “주문 정보”를 확정하는 단계
- 운영 이슈(주소/배송/재고) 대부분이 여기서 발생

## Scope
### 1) Checkout 단계 구성
- Step 1: 배송지(주소)
- Step 2: 배송 옵션(배송방법/희망일 옵션 있으면)
- Step 3: 결제수단 선택(카드/간편결제 등 — MVP는 “모의 PG” 기준)

### 2) 주소 UX
- 배송지 목록/새 배송지 추가
- 기본 배송지 설정
- 폼 validation(필수값/전화번호 포맷)

### 3) 주문 요약
- 아이템 요약, 결제 예정 금액
- “주문하기” 버튼 클릭 시 `Order 생성` 호출

### 4) 에러 처리
- 재고 부족/가격 변경 시 재확인 모달
- 서버 에러 시 재시도/리프레시 안내

## Non-goals
- 회원등급/쿠폰/프로모션 복잡 로직

## DoD
- Checkout에서 주소/배송/결제수단 선택 후 주문 생성까지 정상 동작
- validation 및 에러 핸들링 완비

## Interfaces
- `GET /checkout` (요약 데이터)
- `POST /orders` (주문 생성)
- (옵션) `GET/POST /addresses`

## Files (예시)
- `web-user/src/pages/checkout/CheckoutPage.tsx`
- `web-user/src/components/checkout/AddressForm.tsx`
- `web-user/src/components/checkout/PaymentMethodSelect.tsx`
- `web-user/src/api/checkout.ts`

## Codex Prompt
Implement Checkout UI:
- Multi-section page (address, shipping, payment method, order summary).
- Validate forms, handle stock/price change warnings, and create order on submit.
