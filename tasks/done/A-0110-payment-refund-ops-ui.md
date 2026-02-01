# A-0110 — Payment & Refund Ops UI

## Goal
결제/환불 운영(CS/장애 대응)을 위한 조회/조치 UI.

## Scope
- Payment list/detail
  - 결제 상태(PENDING/APPROVED/FAILED/CANCELED)
  - 실패 사유/PG 응답 요약
- Refund list/detail
  - 부분환불/전체환불
  - 재고 복원(ledger) 연계 상태 표시
- CS 메모/태그(선택)

## Safety / Policy
- 환불/취소는 반드시 RBAC 권한 체크 + audit_log 기록

## API (BFF)
- `GET /admin/payments`
- `GET /admin/payments/{id}`
- `POST /admin/payments/{id}/cancel`
- `GET /admin/refunds`
- `POST /admin/refunds`

## DoD
- 운영자가 결제 실패 원인/상태를 1분 내 파악 가능
- 부분환불 처리 가능(권한/감사로그 포함)

## Codex Prompt
Admin에서 Payment/Refund 운영 UI를 구현하라.
결제/환불 리스트·상세와 환불 실행 폼을 제공하고, 위험 액션은 확인 모달+audit을 전제로 하라.
