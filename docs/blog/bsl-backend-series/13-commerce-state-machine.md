---
title: "13. Commerce 상태머신: 주문/결제/환불"
slug: "bsl-backend-series-13-commerce-state-machine"
series: "BSL Backend Technical Series"
episode: 13
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 13. Commerce 상태머신: 주문/결제/환불

## 핵심 목표
커머스는 API 성공/실패보다 상태 전이를 정확히 통제하는 것이 중요합니다. 이 프로젝트는 주문/결제/환불을 상태머신 + 멱등키 중심으로 구현했습니다.

핵심 구현:
- `services/commerce-service/.../OrderService.java`
- `.../PaymentService.java`
- `.../RefundService.java`
- `.../payment/PaymentStatus.java`
- `.../WebhookRetryScheduler.java`

## 1) 주문 상태머신 (`OrderService.OrderStatus`)
상태:
- `CREATED`
- `PAYMENT_PENDING`
- `PAID`
- `READY_TO_SHIP`
- `SHIPPED`
- `DELIVERED`
- `CANCELED`
- `REFUND_PENDING`
- `REFUNDED`
- `PARTIALLY_REFUNDED`

`canTransitionTo`가 허용하지 않는 전이는 즉시 `invalid_state`로 차단합니다.

대표 전이:
- `CREATED -> PAYMENT_PENDING|CANCELED`
- `PAYMENT_PENDING -> PAID|CANCELED`
- `PAID -> READY_TO_SHIP|REFUND_PENDING|REFUNDED|PARTIALLY_REFUNDED`

## 2) 결제 생성/웹훅 멱등
`PaymentService`는 `idempotencyKey` 중복을 먼저 확인합니다.

웹훅 처리에서 중요한 방어 로직:
1. provider event 중복 감지
2. 서명 검증 실패 시 `invalid_signature`
3. 지원하지 않는 상태는 `ignored_unsupported_status`
4. 현재 상태와 target 상태 불일치면 `invalid_transition` 또는 `invalid_state`

`PaymentStatus.canTransitionTo`로 결제 상태 전이도 별도 통제합니다.

## 3) 캡처 성공 이후 side effect
결제 CAPTURED 이후 연쇄 동작:

1. 주문 `markPaid`
2. 재고 차감 (`DEDUCT`)
3. 재고 ledger 기록
4. 배송 생성 시도
5. 포인트/리워드 반영

이때 일부 하위 동작 실패는 재시도 대상 작업으로 분리합니다.

## 4) 환불 플로우
`RefundService`는 부분/전체 환불을 모두 지원합니다.

핵심 검증:
- 주문 상태가 환불 가능 상태인지
- 환불 수량이 주문 수량을 초과하지 않는지
- idempotency key 재사용 처리

환불 승인 후:
- 상태 `REFUNDED` 또는 `PARTIALLY_REFUNDED`
- 재고 복원(restock) 시도
- restock 실패 시 후속 처리 작업 기록(재시도 가능)

## 5) 웹훅 재시도 스케줄러
`WebhookRetryScheduler`가 실패 웹훅을 배치로 재처리합니다.

제어 포인트:
- 배치 크기
- 최대 시도 횟수
- backoff
- 성공/실패 메트릭

로컬 테스트에서도 “중복 웹훅 + 재시도 + 부분환불” 케이스를 재현할 수 있습니다.

## 로컬 점검 포인트
```bash
# 결제/환불 API 호출 후 상태와 이벤트 테이블 변화를 함께 확인
# (order_event, payment_event, refund, refund_item 등)
```

## 6) 주문/결제 상태 전이 검증의 핵심
상태머신 설계에서 중요한 점은 “허용 전이만 통과”입니다.

1. 주문은 `canTransitionTo`를 통과하지 못하면 즉시 차단됩니다.
2. 결제도 `PaymentStatus.canTransitionTo`로 별도 검증됩니다.
3. 웹훅 입력 상태가 불명확하면 `invalid_current_status`로 실패합니다.

즉, 상태 전이 규칙을 코드로 강제해 데이터 정합성을 보호합니다.

## 7) 웹훅 처리 파이프라인 심화
`processWebhookInternal()` 기준 흐름:

1. webhook event insert(중복이면 duplicate 처리)
2. 서명 검증 실패 시 `invalid_signature`
3. `payment_id` 추출 실패 시 ignored
4. 결제 행 조회 실패 시 ignored
5. target status 해석 실패 시 `unsupported_status`
6. 전이 가능성 검사 후 상태 갱신
7. CAPTURED면 후속 side effect 실행
8. webhook event 상태를 `PROCESSED`로 갱신

웹훅 입력 품질이 낮아도 전체 파이프라인이 붕괴하지 않도록 방어합니다.

## 8) CAPTURED 후 후속 작업 디테일
`applyPostCaptureEffects()`에서 수행하는 실제 작업:

1. 주문 결제 완료 처리
2. 주문 아이템별 재고 차감(ledger idempotency key 포함)
3. 회계/정산 ledger 반영
4. 배송 생성 시도(실패 시 warning)
5. 로열티 포인트 적립

즉, 결제 성공이 주문 도메인 전체 상태를 전파하는 트리거입니다.

## 9) 웹훅 재시도 스케줄러 기본값
`application.yml` 기준:

1. retry enabled=true
2. delay=30000ms
3. initial delay=20000ms
4. batch size=20
5. max attempts=3
6. backoff seconds=30

재시도 횟수를 넘기면 `FAILED`로 종료해 무한 반복을 막습니다.

## 10) 로컬 테스트 시 추천 케이스
1. 같은 웹훅 이벤트를 두 번 보내 duplicate 처리 확인
2. 잘못된 서명으로 `invalid_signature` 확인
3. 허용되지 않는 상태 전이 payload로 `invalid_transition` 확인
4. 부분환불/전체환불 후 주문 상태 변화를 비교
