---
title: "31. Privacy 스크립트: 사용자 데이터 Export/Delete/Purge"
slug: "bsl-backend-series-31-privacy-export-delete-scripts"
series: "BSL Backend Technical Series"
episode: 31
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 31. Privacy 스크립트: 사용자 데이터 Export/Delete/Purge

## 핵심 목표
배포 전 운영 체계와 별개로, 로컬 개발 단계에서 사용자 데이터 lifecycle을 검증할 수 있는 스크립트 세트를 정리합니다.

핵심 구현 파일:
- `scripts/privacy/export_user_data.py`
- `scripts/privacy/delete_user_data.py`
- `scripts/privacy/purge_audit_log.sh`

## 1) export 스크립트 개요
`export_user_data.py`는 `--user-id` 기준으로 여러 테이블을 조회해 JSON 한 파일로 저장합니다.

기본 출력 경로:
- `var/privacy/user_<id>_export.json`

## 2) export 대상 테이블
주요 조회 범위:

- 계정/선호/동의: `user_account`, `user_preference`, `user_consent`
- 활동: `user_recent_query`, `user_recent_view`, `user_feedback`
- 저장: `user_saved_material`, `user_shelf`
- 주소/장바구니/주문/결제/환불/배송 관련 하위 테이블

order/cart를 기준으로 하위 ID를 모아 연관 테이블을 확장 조회합니다.

## 3) export 포맷 특성
- `--pretty` 옵션으로 indent 출력 가능
- datetime 등은 `default=str`로 직렬화
- 조회 결과가 없는 테이블도 빈 배열로 명시

데이터 누락과 "조회 안 함"을 구분할 수 있습니다.

## 4) delete 스크립트 개요
`delete_user_data.py`는 `--user-id` 기준 삭제를 수행합니다.

핵심 옵션:
- `--dry-run`
- `--delete-commerce`

기본은 트랜잭션(`autocommit=False`)으로 동작합니다.

## 5) delete 기본 동작(비상거래 삭제)
기본 모드에서는 commerce 데이터를 전부 하드삭제하지 않고,
`orders.user_id=0`, `shipping_snapshot_json=NULL` 형태로 익명화합니다.

즉, 거래 레코드 보존과 사용자 식별자 제거를 분리합니다.

## 6) delete-commerce 옵션
`--delete-commerce`를 주면 아래까지 하드삭제합니다.

- `order_event`, `order_item`, `payment`
- `refund`, `refund_item`
- `shipment`, `shipment_item`, `shipment_event`
- `orders`

로컬 재현/테스트 환경 초기화에 적합한 옵션입니다.

## 7) 실패 롤백
스크립트에서 예외가 발생하면 `rollback()` 후 예외를 다시 던집니다.

부분 삭제 상태를 남기지 않도록 트랜잭션 경계를 명시한 구현입니다.

## 8) dry-run 용도
`--dry-run`은 실제 삭제 없이 대상 cart/order 수만 출력합니다.

대량 삭제 전 영향 범위를 먼저 확인할 수 있습니다.

## 9) audit 로그 purge
`purge_audit_log.sh`는 `audit_log` 테이블에서 retention 초과 데이터를 삭제합니다.

기본 retention:
- `AUDIT_LOG_RETENTION_DAYS=90`

MySQL CLI로 단일 DELETE 쿼리를 수행합니다.

## 10) 로컬 실행 예시
```bash
python scripts/privacy/export_user_data.py --user-id 101 --pretty
python scripts/privacy/delete_user_data.py --user-id 101 --dry-run
python scripts/privacy/delete_user_data.py --user-id 101
AUDIT_LOG_RETENTION_DAYS=30 bash scripts/privacy/purge_audit_log.sh
```

## 11) 이 스크립트들이 중요한 이유
사이드프로젝트에서도 데이터 lifecycle을 코드로 명시해 두면,

1. 테스트 데이터 정리
2. 사용자 삭제 요청 시나리오 검증
3. 감사 로그 보관 주기 검증

을 자동화할 수 있습니다.

## 12) 구현상 제한
현재 스크립트는 MySQL 직접 접근 방식이므로,
서비스 API 레이어의 정책 검증(권한, 감사 이벤트 생성)까지 포함하지는 않습니다.

따라서 API 정책 검증과 DB 정리 검증은 별도 테스트로 분리하는 것이 안전합니다.
