---
title: "01. SSOT 기준으로 백엔드 구조 고정하기"
slug: "bsl-backend-series-01-ssot-structure"
series: "BSL Backend Technical Series"
episode: 1
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 01. SSOT 기준으로 백엔드 구조 고정하기

## 이 글의 범위
이 시리즈는 로컬에서 실제로 구현하고 검증한 코드 구조를 다룹니다. 핵심은 “어디를 기준(SSOT)으로 보고 개발했는가”입니다.

## 1) SSOT 우선순위
`AGENTS.md`에서 고정한 순서를 그대로 개발 규칙으로 사용했습니다.

1. `contracts/`: 서비스 간 API/Event 계약
2. `data-model/` + `db/`: 원천 도메인 모델과 영속 스키마
3. `infra/opensearch/`: 파생 검색 인덱스 구조
4. `docs/`: 설명 문서(근거는 위 1~3)

이 순서의 의미는 단순합니다. 코드가 먼저가 아니라, 계약/모델이 먼저입니다.

## 2) 실제 저장소에서 역할 분리
- `contracts/*.schema.json`, `contracts/examples/*.sample.json`: 요청/응답/이벤트 shape
- `db/migration/*.sql`: 트랜잭션 도메인 변경 이력
- `infra/opensearch/*.mapping.json`: 검색 필드/분석기/벡터 필드 규격
- `services/*`: 런타임 구현
- `scripts/validate_contracts.py`, `scripts/contract_compat_check.py`: 계약 게이트

특히 계약 검증 스크립트를 코드와 분리해 둔 덕분에, 구현 변경이 계약 파손으로 이어지는지 로컬에서 바로 확인할 수 있습니다.

## 3) 변경 순서 강제
실제 작업 규칙은 아래 두 가지로 고정했습니다.

1. 계약이 바뀌는 작업: `contracts -> code -> tests -> docs`
2. 계약이 안 바뀌는 작업: `code -> tests -> docs`

이 규칙이 없으면 리뷰 단계에서 “의도된 변경인지 실수인지”를 분류하기 어렵습니다.

## 4) Trace/Request ID 기본 전파
`docs/API_SURFACE.md` 기준으로 `trace_id`, `request_id`를 공통 필드로 맞췄습니다. 로컬에서도 서비스 경계가 많기 때문에, 디버깅 난이도 차이가 큽니다.

- 입력 헤더: `x-trace-id`, `x-request-id`
- 응답 필드: `trace_id`, `request_id`

검색/챗/커머스 경로에서 이 두 값이 유지되면 재현 로그를 연결하기 쉬워집니다.

## 5) 문서 작성 규칙(이번 재작성 기준)
이번 시리즈 문서는 다음만 남겼습니다.

1. 코드 경로로 검증 가능한 사실
2. 상태 전이/가드레일/실패 복구
3. 로컬 재현 명령

## 로컬에서 바로 확인할 것
```bash
./scripts/validate_contracts.py
./scripts/contract_compat_check.py
```

첫 편의 결론은 하나입니다. 구조를 먼저 고정해야 뒤편의 검색/랭킹/챗 구현이 흔들리지 않습니다.

## 6) SSOT 충돌이 발생할 때의 우선순위 해석
실제 구현 중 가장 자주 발생하는 문제는 문서와 코드, 스키마와 구현이 동시에 어긋나는 경우입니다. 이때는 아래 순서로 판단합니다.

1. `contracts/**`와 `contracts/examples/**`를 먼저 확인합니다.
2. `data-model/**`, `db/migration/**`로 원천 데이터 정의를 확인합니다.
3. `infra/opensearch/**`로 파생 인덱스 정의를 확인합니다.
4. 마지막으로 `docs/**`를 확인합니다.

즉, 문서 설명이 코드와 다를 때는 코드가 아니라 계약/모델이 기준입니다.

## 7) SSOT 기반 작업 절차(실전)
아래 절차를 반복하면 변경의 성격이 명확해집니다.

1. 변경 요청을 계약 변경/구현 변경으로 분류합니다.
2. 계약 변경이면 스키마와 샘플을 먼저 수정합니다.
3. 구현 코드를 맞춘 뒤 테스트를 실행합니다.
4. 마지막으로 문서를 업데이트합니다.

이 흐름을 지키면 “의도된 스펙 변경”과 “실수로 깨진 스펙”이 구분됩니다.

## 8) 코드 리뷰에서 실제로 보는 체크리스트
SSOT를 지키는지 확인할 때는 아래를 확인합니다.

1. `contracts/*.schema.json` 변경 시 `contracts/examples/*.sample.json`가 같이 변경되었는지
2. `db/migration` 변경 시 서비스 코드가 해당 컬럼/상태 전이를 반영했는지
3. `infra/opensearch` 변경 시 색인/조회 경로가 alias 기준으로 유지되는지
4. `trace_id`, `request_id` 전파가 응답/로그에서 유지되는지

## 9) 로컬 사이드프로젝트에서 특히 중요했던 점
로컬 실행만 하더라도 구조가 흔들리면 개발 속도가 급격히 떨어집니다. 실제로는 기능 구현보다 “기준점 정리”가 먼저였습니다.

1. 계약 게이트를 통과해야 구현을 진행했습니다.
2. 상태머신/가드레일/reason code를 먼저 정의했습니다.
3. 서비스 경계를 고정해 디버깅 범위를 줄였습니다.

이 기준이 뒤편의 검색, 랭킹, 챗 아티클 전체의 공통 토대입니다.
