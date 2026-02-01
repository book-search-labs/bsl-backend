# U-0118 — Web User: 결제 플로우 UI (성공/실패/재시도)

## Goal
결제 과정을 사용자 입장에서 “끊김 없이” 완결한다.
- 결제 시작 → 처리중 → 성공/실패 → 재시도/주문 복귀

## Why
- 결제는 오류/재시도/중복클릭이 매우 흔함
- 멱등키/재시도 설계가 UI에서 명확해야 운영 사고를 줄임

## Scope
### 1) 결제 시작/진행 화면
- “결제 처리 중” 상태(로딩 + 안내)
- 중복 클릭 방지(버튼 disable)

### 2) 성공 화면
- 주문번호, 결제금액, 배송예정 안내
- “주문 상세 보기” CTA

### 3) 실패 화면
- 실패 사유(가능한 범위)
- 재시도 버튼(멱등키 유지)
- “나중에 결제하기/주문으로 돌아가기” 선택지

### 4) 상태 동기화
- 페이지 새로고침/뒤로가기 대응
- `GET /payments/{payment_id}` 또는 `GET /orders/{order_id}`로 상태 재조회

## Non-goals
- 실 PG 결제 UI(카드 입력 폼 등)는 통합 방식에 따라 후속

## DoD
- 결제 성공/실패/재시도가 명확한 UX로 제공됨
- 중복 결제 방지(재시도는 같은 idempotency key로 처리되는 전제)
- 새로고침/복귀에도 상태가 일관됨

## Interfaces
- `POST /payments` (결제 시작)
- `GET /payments/{id}` (상태 조회)
- `POST /payments/{id}/retry` (옵션)
- `GET /orders/{id}` (주문 상태 확인)

## Files (예시)
- `web-user/src/pages/payment/PaymentProcessingPage.tsx`
- `web-user/src/pages/payment/PaymentResultPage.tsx`
- `web-user/src/api/payment.ts`

## Codex Prompt
Implement Payment flow UI:
- Processing, success, failure pages with safe retry.
- Prevent double-submit, re-fetch state on refresh, and link back to order detail.
