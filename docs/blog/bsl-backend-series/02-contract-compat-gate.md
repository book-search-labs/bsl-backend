---
title: "02. JSON Schema 계약 검증 게이트"
slug: "bsl-backend-series-02-contract-compat-gate"
series: "BSL Backend Technical Series"
episode: 2
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 02. JSON Schema 계약 검증 게이트

## 문제
서비스를 여러 개로 나누면, 코드 컴파일이 통과해도 인터페이스가 이미 깨져 있을 수 있습니다. 이 프로젝트에서는 그 위험을 두 단계 게이트로 막았습니다.

## 1) 1차 게이트: schema + sample 정합성 (`scripts/validate_contracts.py`)
이 스크립트는 `SCHEMA_FILES` 매핑에 있는 계약을 고정 검사합니다.

검사 순서:
1. 스키마 파일 존재
2. 샘플 파일 존재
3. Draft 2020-12 validator로 샘플 검증
4. 실패 시 경로 단위 에러 출력 후 비정상 종료

구현 포인트:
- validator: `Draft202012Validator`
- 로컬 `$ref` 해석: `RefResolver(base_uri=schema_path.as_uri(), ...)`
- 샘플이 하나라도 깨지면 전체 실패

즉, “스키마만 맞춘 상태”를 통과시키지 않습니다.

## 2) 2차 게이트: 베이스 브랜치 대비 호환성 (`scripts/contract_compat_check.py`)
기본 비교 기준은 `origin/develop`입니다.

주요 차단 규칙:
- type 축소(예: `string|integer -> string`)
- enum 축소
- required 필드 추가
- `additionalProperties`를 더 엄격하게 변경
- property 제거
- array item 제약의 파괴적 변경
- OpenAPI path/operation 제거

핵심은 “현재 브랜치에서 통과”가 아니라 “이전 계약과도 호환”입니다.

## 3) 계약 변경과 구현 변경을 분리하는 이유
같은 PR에서 계약과 구현을 같이 바꿀 수는 있습니다. 하지만 의도 없는 계약 파손은 반드시 잡아야 합니다.

그래서 이 저장소는 계약 변경 자체를 명시적 작업으로 취급합니다.
- 계약 변경: `contracts/**` + example 동반 수정
- 구현 변경: 계약 불변 상태에서 서비스 코드만 수정

## 4) 로컬 실패 케이스 예시
대표적으로 자주 걸리는 케이스는 다음입니다.

1. schema는 바꿨는데 `contracts/examples/*.sample.json`를 안 고침
2. 응답에 필수 필드를 추가했는데 하위 호환 고려 누락
3. enum 값 정리한다고 기존 값을 제거함

이때 게이트가 먼저 실패해 런타임 오류 전에 문제를 잡습니다.

## 5) 실행 명령
```bash
./scripts/validate_contracts.py
./scripts/contract_compat_check.py
```

프로젝트 전체 테스트 엔트리포인트에서는 아래로 포함됩니다.
```bash
./scripts/test.sh
```

계약 게이트를 통과하지 못한 구현은 이후 검색/랭킹/챗 품질 논의 자체가 의미가 없습니다.

## 6) `validate_contracts.py` 내부 동작 심화
이 스크립트는 단순 파일 유무 체크가 아니라, 계약을 실제 데이터로 실행 검증합니다.

1. `SCHEMA_FILES`에 선언된 쌍만 검사합니다.
2. 각 스키마/샘플 쌍에 대해 Draft 2020-12 validator를 생성합니다.
3. local `$ref`를 해석하기 위해 `RefResolver`를 사용합니다.
4. 에러는 JSON path 단위로 수집해 출력합니다.

이 설계 덕분에 하위 스키마(`$ref`) 누락도 조기에 발견됩니다.

## 7) `contract_compat_check.py` 파괴적 변경 판정 기준
호환성 체크는 아래 케이스를 파괴적 변경으로 봅니다.

1. 타입 축소
2. enum 축소
3. required 항목 추가
4. `additionalProperties` 강화
5. 기존 property 제거
6. array `items` 제약 제거/변경
7. OpenAPI path/operation 제거

핵심은 “신규 기능 추가”보다 “기존 소비자 깨짐 여부”를 먼저 본다는 점입니다.

## 8) 실제로 자주 발생한 실패 패턴
1. 스키마는 바꿨지만 샘플 JSON을 갱신하지 않은 경우
2. 응답 필드를 mandatory로 바꾸면서 하위 호환 검토를 누락한 경우
3. enum 정리 과정에서 기존 값이 삭제된 경우
4. OpenAPI에서 기존 endpoint를 제거한 경우

이 실패 패턴은 코드를 실행하기 전 단계에서 바로 차단됩니다.

## 9) 계약 변경이 필요할 때의 권장 방식
1. 기존 버전을 유지합니다.
2. breaking change가 필요하면 `v2` 스키마를 신규로 추가합니다.
3. 샘플 payload를 버전별로 함께 추가합니다.
4. 구현에서 버전 라우팅 또는 backward compatibility를 둡니다.

로컬에서도 이 원칙을 지키면 이후 서비스 분리가 쉬워집니다.

## 10) 실전 실행 프로필
아래 순서로 실행하면 실패 원인 분리가 쉽습니다.

```bash
./scripts/validate_contracts.py
./scripts/contract_compat_check.py
./scripts/test.sh
```

첫 두 단계에서 실패하면 코드 로직을 보기 전에 계약부터 수정하는 것이 효율적입니다.
