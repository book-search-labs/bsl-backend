---
title: "17. 개인정보 Export/Delete 스크립트"
slug: "bsl-backend-series-17-privacy-export-delete"
series: "BSL Backend Technical Series"
episode: 17
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 17. 개인정보 Export/Delete 스크립트

## 핵심 목표
개인정보 처리를 ad-hoc SQL이 아니라 재현 가능한 스크립트로 고정해, 로컬에서도 export/delete/anonymize를 검증 가능하게 만들었습니다.

핵심 파일:
- `scripts/privacy/export_user_data.py`
- `scripts/privacy/delete_user_data.py`
- `scripts/privacy/purge_audit_log.sh`

## 1) Export 스크립트
입력:
- `--user-id` (필수)
- `--output` (옵션)
- `--pretty` (옵션)

조회 범위는 사용자 계정/활동/커머스 연관 테이블까지 포함합니다.

예시 그룹:
- 계정/동의: `user_account`, `user_preference`, `user_consent`
- 활동: `user_saved_material`, `user_recent_query`, `user_feedback`
- 커머스: `orders`, `payment`, `refund`, `shipment` 관련 테이블

즉, user_id 기준 데이터 footprint를 한 번에 수집할 수 있습니다.

## 2) Delete/Anonymize 스크립트
`delete_user_data.py`는 안전장치를 갖고 있습니다.

주요 옵션:
- `--user-id`
- `--dry-run`
- `--delete-commerce` (커머스 데이터까지 삭제 범위 확장)

`dry-run`으로 영향 범위를 먼저 확인한 뒤 실제 삭제를 수행하는 흐름을 강제했습니다.

## 3) 감사 로그 purge
`purge_audit_log.sh`는 보관 기간 기반으로 오래된 로그를 제거합니다.

보통 환경변수(예: retention days)를 받아 SQL purge를 수행합니다.

## 4) 왜 스크립트화가 중요한가
개인정보 처리는 “매번 사람이 기억해서 하는 작업”이면 실수가 반복됩니다. 스크립트화하면 아래가 좋아집니다.

1. 동일 입력에 동일 동작
2. dry-run 기반 사전 검토
3. 처리 범위의 코드 리뷰 가능

## 로컬 실행 예시
```bash
python scripts/privacy/export_user_data.py --user-id 123 --pretty
python scripts/privacy/delete_user_data.py --user-id 123 --dry-run
```

## 5) Export 스크립트 세부 동작
`export_user_data.py`는 사용자 기본 테이블뿐 아니라 주문 연관 하위 테이블까지 따라갑니다.

1. `orders` 조회
2. `order_item`, `order_event`, `payment`, `refund` 조회
3. refund가 있으면 `refund_item` 조회
4. shipment가 있으면 `shipment_item`, `shipment_event` 조회

즉, user_id 기반으로 연결 가능한 상위/하위 데이터를 한 번에 덤프합니다.

## 6) Delete 스크립트의 분기
`delete_user_data.py`는 `--delete-commerce` 여부에 따라 동작이 다릅니다.

1. 옵션 미사용: 커머스는 hard delete 대신 익명화(`orders.user_id=0` 등)
2. 옵션 사용: 주문/결제/환불/배송 연관 테이블까지 삭제

민감한 상거래 데이터 손실을 방지하기 위해 기본값을 보수적으로 둔 구조입니다.

## 7) 트랜잭션/롤백 처리
삭제 스크립트는 autocommit=false로 실행됩니다.

1. 중간 예외 발생 시 rollback
2. 전체 성공 시 commit

부분 삭제 상태를 최소화하기 위한 기본 안전장치입니다.

## 8) 감사 로그 정리 스크립트
`purge_audit_log.sh`는 `AUDIT_LOG_RETENTION_DAYS` 기준으로 SQL delete를 수행합니다.

```bash
AUDIT_LOG_RETENTION_DAYS=90 ./scripts/privacy/purge_audit_log.sh
```

로컬에서도 retention 정책을 코드로 재현할 수 있습니다.

## 9) 추천 실행 순서
1. export 실행
2. delete dry-run 실행
3. 삭제 실행 또는 익명화 실행
4. audit purge 실행
5. 다시 export해서 잔존 데이터 확인

개인정보 처리 작업을 검증 가능한 단계로 분해하는 것이 핵심입니다.
