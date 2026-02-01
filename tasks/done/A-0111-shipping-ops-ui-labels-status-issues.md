# A-0111 — Shipping Ops UI (labels/status/issues)

## Goal
배송 운영(출고/송장/상태/이슈 처리)을 위한 UI.

## Scope
- Shipment list/detail
  - 택배사, 송장번호, 상태(READY/SHIPPED/DELIVERED/EXCEPTION)
- 라벨/송장 등록(선택: CSV 업로드 or 단건 입력)
- 배송 이슈 관리
  - 분실/지연/반송 등 상태 기록 + 메모

## API (BFF)
- `GET /admin/shipments`
- `GET /admin/shipments/{id}`
- `POST /admin/shipments/{id}/label`
- `POST /admin/shipments/{id}/status`

## DoD
- 운영자가 주문→출고→배송 추적 상태를 한 화면에서 확인
- 송장 등록/상태 업데이트가 가능(권한/감사로그)

## Codex Prompt
Admin에서 Shipping Ops UI를 구현하라.
Shipment 리스트/상세/송장등록/상태변경을 제공하고 audit_log 연동을 전제로 하라.
