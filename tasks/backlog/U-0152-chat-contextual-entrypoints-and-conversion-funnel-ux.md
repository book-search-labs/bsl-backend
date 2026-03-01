# U-0152 — Chat Contextual Entrypoints + Conversion Funnel UX

## Priority
- P1

## Dependencies
- U-0150, U-0151
- B-0392, B-0393

## Goal
상세/장바구니/주문내역 화면에서 문맥형 챗 진입점을 제공해 사용자 문제 해결 전환율을 높인다.

## Scope
### 1) Contextual entrypoints
- 상세: "이 책 배송/반품 문의" 버튼
- 장바구니: "결제 전 배송비/할인 확인" 버튼
- 주문내역: "현재 주문 상태 문의" 버튼
- 진입 시 context payload(docId/orderId/cartState) 자동 주입

### 2) Guided conversion funnel
- 챗 내 CTA를 단계형(확인→실행→완료)으로 구성
- 실패 시 즉시 대체 경로(재시도/티켓/상담) 제시
- 각 단계 이탈률 측정 이벤트 정의

### 3) Accessibility & mobile
- 모바일 하단 safe-area 침범 방지
- 스크린리더 레이블/키보드 포커스 순서 보장

## DoD
- 문맥형 진입점 클릭 후 해결 완료율 상승
- 챗 전환 퍼널(진입/진행/완료) 지표 확보
- 모바일 접근성 QA 통과

## Codex Prompt
Improve chat conversion UX:
- Add contextual entrypoints on detail/cart/order pages.
- Pass context payloads into the widget automatically.
- Build measurable step-based conversion funnel with fallback actions.
