---
title: "19. Query Prepare 내부 파이프라인: Normalize -> Analyze -> Understanding"
slug: "bsl-backend-series-19-query-prepare-normalize-understanding"
series: "BSL Backend Technical Series"
episode: 19
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 19. Query Prepare 내부 파이프라인: Normalize -> Analyze -> Understanding

## 핵심 목표
`/query/prepare`가 단순 전처리 API가 아니라, 검색 전략을 결정하는 구조화 단계라는 점을 코드 기준으로 정리합니다.

핵심 구현 파일:
- `services/query-service/app/api/routes.py`
- `services/query-service/app/core/normalize.py`
- `services/query-service/app/core/analyzer.py`
- `services/query-service/app/core/understanding.py`

## 1) normalize 단계: 규칙 체인
`normalize_query_details()`는 아래 순서를 고정으로 수행합니다.

1. NFKC 정규화 (`_nfkc`)
2. 제어문자 제거 (`_strip_control_chars`)
3. trim
4. casefold
5. 구두점 정규화 (`_normalize_punctuation`)
6. 권차 토큰 정규화 (`_normalize_volume_tokens`)
7. 공백 collapse
8. 치환 규칙 적용 (`_apply_replacements`)

적용된 규칙은 `rulesApplied`로 QC 응답에 포함됩니다.

## 2) NFKC + 한글 자모 보정 포인트
`normalize.py`는 ICU(`Normalizer2`)가 있으면 ICU NFKC를 우선 사용하고, 실패 시 `unicodedata.normalize("NFKC")`로 폴백합니다.

또한 `_JAMO_TO_COMPAT` 매핑으로 분해 자모를 호환 자모로 다시 맞춰, 키보드 입력 편차에서 노이즈를 줄였습니다.

## 3) 권차/로마숫자 정규화 규칙
`_normalize_volume_tokens()`는 도서 도메인에서 중요한 권차 표현을 통일합니다.

예시 처리:
- `01 권`, `제 01권` -> `1권`
- `vol. 03`, `v3` -> `3권`
- `vol.iv`, `iv권` -> `4권`

이 덕분에 후속 단계에서 `volume` 슬롯 추출 정확도가 안정됩니다.

## 4) 외부 치환 규칙 파일
환경변수 `NORMALIZATION_RULES_PATH`가 설정되면 JSON 규칙을 로딩합니다.

지원 포맷:
- 문자열 치환 (`from`/`to`)
- 정규식 치환 (`regex=true`)

규칙은 지연 로드되고 `reload_normalization_rules()`로 재로딩할 수 있습니다.

## 5) analyzer 단계: mode 결정
`analyze_query()`는 normalize 결과를 바탕으로 아래 시그널을 계산합니다.

- `volume`
- `isbn`
- `series_hint`
- `lang`, `lang_confidence`
- `is_mixed`, `is_chosung`

mode 결정 우선순위:
1. `isbn`
2. `chosung`
3. `mixed`
4. `normal`

## 6) canonical key 생성 규칙
`_build_canonical_key()`는 다음 조합을 SHA-256으로 해시한 뒤 16자 prefix를 사용합니다.

구성 요소:
- `norm`
- `mode`
- `locale`
- `vol`, `isbn`, `series` (존재 시)

결과 형식은 `ck:<16hex>`입니다.

## 7) understanding: 명시 필터 파싱
`parse_understanding()`은 `author:`, `title:`, `isbn:`, `series:`, `publisher:` 구문을 정규식으로 추출합니다.

중요 동작:
- ISBN 10자리 입력은 내부에서 ISBN13으로 변환
- 명시 필터가 있으면 `preferred_fields`를 logical field로 구성
- `residual_text`를 분리해 자유 텍스트 질의로 전달

## 8) explicit filter의 실제 매핑
ISBN이 파싱되면 `filters`에 아래 구조가 생성됩니다.

- `scope: CATALOG`
- `logicalField: isbn13`
- `op: eq`
- `value: <isbn13 혹은 배열>`

즉, Query Service에서 생성한 구조가 Search Service의 필터 변환 로직으로 바로 연결됩니다.

## 9) final query 선택 로직
`routes.py::_resolve_final_text()`는 아래 우선순위를 사용합니다.

1. `residual_text` 있으면 `explicit_residual`
2. explicit 구문만 있고 residual이 비면 엔티티 재조합(`explicit_entities`)
3. 그 외에는 `norm`

이 값이 `query.final`로 내려가고, Search Service가 실제 검색 텍스트로 사용합니다.

## 10) retrievalHints 자동 보정
`_build_qc_v11_response()`는 understanding 결과를 이용해 힌트를 보정합니다.

- `preferredLogicalFields` 주입
- `filters` 주입
- ISBN-only 상황에서 `vector.enabled=false`, `rerank.enabled=false`

즉, QC 단계에서 "불필요한 비용 단계"를 미리 차단합니다.

## 11) 캐시 키/TTL 전략
prepare 분석 캐시는 아래 키 규칙을 사용합니다.

- key: `qs:norm:{version}:{digest}`
- env:
  - `QS_NORM_CACHE_VERSION`
  - `QS_NORM_CACHE_TTL_SEC` (기본 3600)

enhance 캐시와 deny 캐시도 버전/TTL이 분리되어 있습니다.

## 12) 로컬 검증 포인트
```bash
curl -sS http://localhost:8001/query/prepare \
  -H 'Content-Type: application/json' \
  -d '{"query":{"raw":"author:한강 isbn:9788936434120 소년이 온다"}}' | jq
```

확인할 필드:
1. `query.final`, `query.finalSource`
2. `understanding.entities`, `understanding.constraints`
3. `retrievalHints.filters`, `retrievalHints.lexical.preferredLogicalFields`
4. `query.normalized.rulesApplied`

## 13) 이 단계를 분리한 이유
검색 품질 문제를 추적할 때, "정규화 실패인지", "의도 파싱 실패인지", "검색기 실행 실패인지"를 분리해야 수정 속도가 올라갑니다.

`/query/prepare`를 독립 계약으로 둔 이유는 바로 이 디버깅 분해능 때문입니다.
