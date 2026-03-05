---
title: "05. Index Writer 재색인 상태머신"
slug: "bsl-backend-series-05-index-writer-state-machine"
series: "BSL Backend Technical Series"
episode: 5
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 05. Index Writer 재색인 상태머신

## 핵심 목표
재색인을 단발성 배치가 아니라, 중단/재개/재시도 가능한 상태머신으로 구현해 로컬에서도 장애 복구 흐름을 재현 가능하게 만들었습니다.

핵심 구현:
- `services/index-writer-service/app/reindex.py`
- `services/index-writer-service/app/main.py`
- `services/index-writer-service/app/db.py`

## 1) 상태 전이
`run_job()` 기준 상태 순서는 아래와 같습니다.

1. `PREPARE`
2. `BUILD_INDEX`
3. `BULK_LOAD`
4. `VERIFY`
5. `ALIAS_SWAP`
6. `CLEANUP`
7. `SUCCESS`

중간 제어 상태:
- `PAUSED`

오류 종료:
- `FAILED`

단계가 명확해서 실패 지점 추적이 쉽고, 특정 단계부터 재개하기도 용이합니다.

## 2) 실패 내성 설계
`BULK_LOAD` 단계에 방어 로직이 집중되어 있습니다.

1. 문서 단위 오류를 `reindex_error`에 누적
2. 일시 오류 대상 재시도(backoff)
3. 누적 실패가 `REINDEX_MAX_FAILURES`를 넘으면 fail-fast

즉, 일부 실패는 허용하되 무한 재시도는 막습니다.

## 3) pause/resume/retry API
`main.py`의 내부 API로 잡 제어가 가능합니다.

- pause
- resume
- retry

상태머신 기반이라 “현재 단계 + 진행률” 기준으로 안전하게 이어서 실행할 수 있습니다.

## 4) alias 전환과 버전 기록
`ALIAS_SWAP` 단계에서 검색 alias를 새 물리 인덱스로 옮깁니다.

동시에 버전 메타(`search_index_version`, `search_index_alias`)를 업데이트해, 현재 active 인덱스를 추적할 수 있게 했습니다.

## 5) 왜 이 방식이 중요한가
색인 작업은 실패 확률이 높은 I/O 작업입니다. 상태머신이 없으면 실패 시 전량 재실행만 가능하고, 디버깅 비용이 커집니다.

이 구현은 다음을 보장합니다.

1. 단계별 가시성
2. 부분 실패 기록
3. 재개 가능한 제어면

## 로컬 검증 포인트
```bash
# index-writer 서비스 기동 후
curl -sS http://localhost:<index-writer-port>/internal/index/reindex-jobs/<job_id> | jq
```

상태 전이 로그가 `PREPARE -> ... -> SUCCESS`로 보이는지 먼저 확인합니다.

## 6) 단계별 입력/출력 관점에서 보는 상태머신
각 단계는 명확한 입력/출력을 가집니다.

1. `PREPARE`: 기존 alias 해석, target index 결정
2. `BUILD_INDEX`: mapping으로 물리 인덱스 생성
3. `BULK_LOAD`: MySQL 배치 조회 + OpenSearch bulk 적재
4. `VERIFY`: count/sample query 검증
5. `ALIAS_SWAP`: read/write alias 교체
6. `CLEANUP`: 필요 시 구 인덱스 정리
7. `SUCCESS`/`FAILED`: 종료 상태 기록

이 구조 덕분에 실패 지점을 단계 단위로 국소화할 수 있습니다.

## 7) `BULK_LOAD` 내성 설계 심화
bulk 처리에서 중요한 제어값:

1. `OS_BULK_SIZE`
2. `OS_RETRY_MAX`
3. `OS_RETRY_BACKOFF_SEC`
4. `REINDEX_MAX_FAILURES`
5. `REINDEX_BULK_DELAY_SEC`

실패 문서는 `reindex_error`에 누적하고, 누적 실패가 임계치를 넘으면 즉시 중단합니다.

## 8) alias swap 실제 동작
코드에서는 아래 액션을 묶어서 수행합니다.

1. 기존 `doc_read_alias` remove
2. 기존 `doc_alias(write)` remove
3. 새 인덱스에 read alias add
4. 새 인덱스에 write alias add(`is_write_index=true`)

전환 후 버전 상태를 `ACTIVE`/`DEPRECATED`로 갱신합니다.

## 9) pause/resume/retry의 실제 의미
1. `pause`: 현재 진행률을 보존하고 `PAUSED`
2. `resume`: 상태를 `RESUME`로 바꿔 worker가 재수행
3. `retry`: 실패 잡을 `RETRY`로 전환

중요한 점은 “처음부터 초기화”가 아니라 기존 progress를 기준으로 이어간다는 점입니다.

## 10) 로컬 검증 시 추천 로그 체크
1. 단계 전이 로그(`PREPARE -> ... -> SUCCESS`)
2. bulk 통계(`indexed/failed/retried`)
3. verify 샘플 쿼리 hit 수
4. alias 최종 대상 인덱스

이 네 항목을 확인하면 재색인 파이프라인 품질을 빠르게 판단할 수 있습니다.
