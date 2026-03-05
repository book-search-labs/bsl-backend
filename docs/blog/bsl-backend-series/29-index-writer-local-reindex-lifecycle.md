---
title: "29. Index Writer 로컬 재색인 생명주기: 상태 전이와 Alias 전환"
slug: "bsl-backend-series-29-index-writer-local-reindex-lifecycle"
series: "BSL Backend Technical Series"
episode: 29
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 29. Index Writer 로컬 재색인 생명주기: 상태 전이와 Alias 전환

## 핵심 목표
Index Writer는 대량 색인을 "한 번 실행"이 아니라 상태머신으로 처리합니다. 로컬 환경에서의 상태 전이와 복구 지점을 코드로 정리합니다.

핵심 구현 파일:
- `services/index-writer-service/app/main.py`
- `services/index-writer-service/app/db.py`
- `services/index-writer-service/app/reindex.py`
- `services/index-writer-service/app/config.py`

## 1) 작업 획득(Claim)
`Database.claim_next_job()`는 상태가 `CREATED|RESUME|RETRY`인 작업을
`FOR UPDATE`로 하나 잡고 `PREPARE`로 전이합니다.

즉, 다중 워커에서도 동일 작업 중복 실행을 줄이는 구조입니다.

## 2) API 제어 엔드포인트
`main.py`가 제공하는 제어 엔드포인트:

- 작업 생성: `POST /internal/index/reindex-jobs`
- 조회: `GET /internal/index/reindex-jobs/{job_id}`
- 일시중지: `POST .../pause`
- 재개: `POST .../resume`
- 재시도: `POST .../retry`

로컬에서 상태 전이를 강제로 재현하기 쉽습니다.

## 3) ReindexRunner 단계
`run_job()`의 주요 상태 전이:

1. `PREPARE`
2. `BUILD_INDEX`
3. `BULK_LOAD`
4. `VERIFY`
5. `ALIAS_SWAP`
6. `CLEANUP`
7. `SUCCESS` (실패 시 `FAILED`)

각 단계마다 `progress_json`이 갱신됩니다.

## 4) 대상 인덱스 생성 규칙
`to_physical`이 없으면 `generate_index_name(prefix)`로 새 물리 인덱스를 생성합니다.

`delete_existing=true`면 prefix 매칭 인덱스를 정리할 수 있지만, 기본은 false라 기존 인덱스를 보존합니다.

## 5) bulk 처리와 재시도
`bulk_request()`는 아래 정책을 사용합니다.

- HTTP transient 상태코드면 지수 백오프 재시도
- item 단위 에러도 transient면 부분 재시도
- 최종 실패는 `reindex_error` 테이블 기록

재시도 소진 시 `retry_exhausted`로 기록합니다.

## 6) pause 동작
`bulk_load()` 반복 중 `should_pause()`가 true이면

1. 현재 progress 저장
2. 상태 `PAUSED` 전이
3. 즉시 반환

중간 커서(`last_material_id`)가 남아 이후 `RESUME` 재개가 가능합니다.

## 7) alias swap 절차
`ALIAS_SWAP` 단계에서 기존 read/write alias를 remove한 뒤 새 인덱스를 add합니다.

동시에 DB의 `search_index_alias`와 `search_index_version` 상태를 업데이트합니다.

## 8) 검증 단계
`VERIFY`에서는 인덱스 refresh 후 샘플 질의를 실행해 최소 정상성을 확인합니다.

실패 시 `ReindexException`으로 `FAILED` 전이되고 error payload가 저장됩니다.

## 9) 설정값(핵심)
`Settings.from_env()` 기본값:

- `MYSQL_BATCH_SIZE=1000`
- `OS_BULK_SIZE=1000`
- `OS_RETRY_MAX=3`
- `OS_RETRY_BACKOFF_SEC=1.0`
- `REINDEX_MAX_FAILURES=1000`
- `JOB_POLL_INTERVAL_SEC=2`

## 10) 문서 빌드 포인트
`build_document()`는 material/override/identifier/agent/concept/kdc를 조합해 색인 문서를 만듭니다.

ISBN10->13 변환, 다국어 title 분리, author flatten, kdc path 계산까지 이 단계에서 수행합니다.

## 11) 로컬 검증 플로우
1. reindex job 생성
2. 상태가 `BULK_LOAD`일 때 pause 호출
3. 상태/커서 확인
4. resume 호출 후 `SUCCESS`까지 진행
5. alias가 새 physical index를 가리키는지 확인

## 12) 구현상 의도
색인은 실패 가능성이 높기 때문에, "성공 경로"보다 "중단/재시도/부분 실패 기록"이 더 중요합니다.

이 서비스는 그 지점을 상태와 progress로 명시해 로컬에서도 재현 가능하게 만든 구현입니다.
