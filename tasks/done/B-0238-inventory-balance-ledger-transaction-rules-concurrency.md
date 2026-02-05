# B-0238 — Inventory: balance/ledger + transaction rules (reserve/release/deduct/restock)

## Goal
커머스의 핵심인 **재고 일관성**을 “운영형”으로 설계/구현한다.

- 단일 숫자 재고가 아니라 **ledger(원장)** 기반으로
- 동시성/재시도/중복 요청에서도 깨지지 않게
- 상태 전이: reserve → (pay) deduct / (cancel/timeout) release → restock

## Background
- 결제/주문은 실패/재시도가 기본이다.
- 단순 `inventory = inventory - n`은 중복 요청/레이스에서 깨짐.
- 그래서 **(1) idempotency key + (2) ledger append + (3) 현재 잔고(balance)**가 필요.

## Scope
### 1) Data model (recommended)
- `inventory_balance`
  - sku_id (PK)
  - on_hand_qty
  - reserved_qty
  - available_qty (computed = on_hand - reserved) 또는 컬럼 유지
  - updated_at
- `inventory_ledger`
  - ledger_id (PK)
  - sku_id
  - event_type: RESERVE / RELEASE / DEDUCT / RESTOCK / ADJUST
  - qty (signed or positive + type)
  - idempotency_key (unique)
  - ref_type/ref_id (ORDER_ID, PAYMENT_ID 등)
  - created_at

### 2) Transaction rules
- RESERVE(qty):
  - 조건: available >= qty
  - reserved += qty
  - ledger append (RESERVE)
- RELEASE(qty):
  - 조건: reserved >= qty (또는 min clamp 정책)
  - reserved -= qty
  - ledger append (RELEASE)
- DEDUCT(qty):
  - 조건: reserved >= qty
  - reserved -= qty
  - on_hand -= qty
  - ledger append (DEDUCT)
- RESTOCK(qty):
  - on_hand += qty
  - ledger append (RESTOCK)

### 3) Concurrency control (MySQL 기준)
- `SELECT ... FOR UPDATE`로 `inventory_balance` row 락
- 트랜잭션 안에서 조건 체크 → update → ledger insert
- ledger insert는 `UNIQUE(idempotency_key)`로 멱등 처리

### 4) API (internal or public)
- GET `/api/v1/inventory/{skuId}` (balance 조회)
- POST `/api/v1/inventory/{skuId}/reserve`
- POST `/api/v1/inventory/{skuId}/release`
- POST `/api/v1/inventory/{skuId}/deduct`
- POST `/api/v1/inventory/{skuId}/restock`
  Request includes:
- qty
- idempotency_key
- ref_type/ref_id

### 5) Failure handling
- idempotency_key 재요청 → 200 OK with previous result (or 409 + stored result; 정책 고정)
- reserve 실패 → 409 INSUFFICIENT_STOCK
- 부분 성공 금지: balance update/ledger insert는 같은 tx에서 원자적으로

## Non-goals
- 주문 상태머신(=B-0240)과 완전 연동은 다음 티켓에서
- 분산락/멀티 DB (v1은 단일 MySQL 트랜잭션)

## DoD
- 위 테이블/제약조건/트랜잭션 규칙이 구현됨
- 동시 reserve 100회 테스트에서 음수/불일치 0
- idempotency 재시도에서 중복 차감 0
- ledger로 이벤트 추적 가능

## Observability
- metrics:
  - inventory_reserve_total{status}
  - inventory_deduct_total{status}
  - inventory_idempotent_hit_total
- logs:
  - sku_id, qty, idempotency_key, ref_id, before/after

## Codex Prompt
Implement inventory with balance + ledger:
- Use MySQL row locking (SELECT FOR UPDATE) and append-only ledger with unique idempotency_key.
- Provide reserve/release/deduct/restock operations and balance 조회.
- Add concurrency tests and idempotency retry tests.
- Document transaction rules and error codes.
