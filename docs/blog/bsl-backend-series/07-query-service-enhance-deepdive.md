---
title: "07. Query Enhance 알고리즘 심화"
slug: "bsl-backend-series-07-query-enhance-deep-dive"
series: "BSL Backend Technical Series"
episode: 7
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 07. Query Enhance 알고리즘 심화

## 핵심 목표
`/query/enhance`를 단순 문자열 보정이 아니라, 예산/쿨다운/실패 복구를 가진 정책 엔진으로 만들었습니다.

핵심 구현:
- `services/query-service/app/core/enhance.py`
- `services/query-service/app/core/spell.py`
- `services/query-service/app/core/rewrite.py`
- `services/query-service/app/core/rag_candidates.py`
- `services/query-service/app/core/rewrite_log.py`

## 1) Gate 평가 로직 (`evaluate_gate`)
enhance 진입 전 아래 조건을 순서대로 검사합니다.

1. reason 허용 여부
2. ISBN 질의 여부 (`ISBN_QUERY`면 skip)
3. score gap 임계치
4. 최소 latency budget
5. 전역 윈도우 예산
6. 질의별 cooldown
7. 질의별 시간당 상한

대표 skip code:
- `NO_REASON`
- `ISBN_QUERY`
- `SCORE_GAP_HIGH`
- `LOW_BUDGET`
- `BUDGET_EXCEEDED`
- `COOLDOWN_HIT`
- `PER_QUERY_CAP`

## 2) 전략 선택(중요)
gate 통과 후 reason에 따라 전략을 고릅니다.

- `SPELL_THEN_REWRITE`
- `REWRITE_ONLY`
- `SPELL_ONLY`
- `RAG_REWRITE`

문자열이 애매할수록 spell 우선, 의도 확장이 필요하면 rewrite, 근거 후보가 충분하면 RAG rewrite로 분기합니다.

## 3) Spell 안전장치 (`spell.py`)
환경변수로 허용 범위를 제어합니다.

- provider/endpoint: `QS_SPELL_PROVIDER`, `QS_SPELL_URL`, `QS_SPELL_PATH`
- timeout/model: `QS_SPELL_TIMEOUT_SEC`, `QS_SPELL_MODEL`
- 길이/거리 가드:
  - `QS_SPELL_LEN_RATIO_MIN`, `QS_SPELL_LEN_RATIO_MAX`
  - `QS_SPELL_EDIT_DISTANCE_RATIO_MAX`
  - `QS_SPELL_MAX_LEN`

치환 품질이 낮거나 과도한 변형이면 후보를 reject합니다.

## 4) Rewrite 안전장치 (`rewrite.py`)
rewrite도 모델 출력을 무조건 신뢰하지 않습니다.

- endpoint: `QS_REWRITE_URL`, `QS_REWRITE_PATH`
- timeout/model: `QS_REWRITE_TIMEOUT_SEC`, `QS_REWRITE_MODEL`
- 최대 길이: `QS_REWRITE_MAX_LEN`

반려 케이스:
- `invalid_json`
- `too_long`
- `no_change`

즉, JSON 포맷/길이/실질 변경 여부를 모두 통과해야 최종 쿼리로 채택됩니다.

## 5) RAG 후보 기반 rewrite (`rag_candidates.py`)
RAG rewrite는 검색 인덱스 후보를 참고해 query expansion을 합니다.

- `QS_RAG_REWRITE_TOP_K`
- `QS_RAG_REWRITE_TIMEOUT_SEC`
- `QS_OS_URL`, `QS_BOOKS_DOC_ALIAS`

후보 수가 적거나 timeout이면 fallback(`rewrite_only`)로 수렴합니다.

## 6) 캐시와 실패 로그
`routes.py`에는 enhance 캐시/deny 캐시 버전이 분리되어 있습니다.

- `QS_ENH_CACHE_VERSION`, `QS_ENH_CACHE_TTL_SEC`
- `QS_ENH_DENY_CACHE_VERSION`, `QS_ENH_DENY_CACHE_TTL_SEC`

`rewrite_log.py`는 sqlite(`query_rewrite_log`)에 실패 태그와 replay payload를 남깁니다. 실패 케이스 재현에 매우 유용합니다.

## 로컬 점검
```bash
curl -sS http://localhost:8001/query/enhance \
  -H 'Content-Type: application/json' \
  -d '{"query":"해리 포터", "reason":"ZERO_RESULTS", "signals":{"latency_budget_ms":400}}' | jq
```

응답의 `decision`, `strategy`, `reason_codes`, `cache_hit`를 같이 확인하면 정책 동작을 빠르게 검증할 수 있습니다.

## 7) Gate 설정 기본값과 의미
`enhance.py` 기본 설정값은 아래와 같습니다.

1. `QS_ENHANCE_SCORE_GAP_THRESHOLD=0.05`
2. `QS_ENHANCE_MIN_LATENCY_BUDGET_MS=200`
3. `QS_ENHANCE_WINDOW_SEC=60`
4. `QS_ENHANCE_MAX_PER_WINDOW=60`
5. `QS_ENHANCE_COOLDOWN_SEC=300`
6. `QS_ENHANCE_MAX_PER_QUERY_PER_HOUR=10`

즉, 품질 조건과 비용 조건을 동시에 통과해야 enhance가 실행됩니다.

## 8) strategy 매핑 상세
reason에 따른 기본 매핑은 다음과 같습니다.

1. `ZERO_RESULTS -> SPELL_THEN_REWRITE`
2. `LOW_RESULTS -> REWRITE_ONLY`
3. `HIGH_OOV -> SPELL_ONLY`
4. `LOW_CONFIDENCE -> REWRITE_ONLY`
5. `USER_EXPLICIT -> RAG_REWRITE`

추가로 mode가 `chosung`이면 `REWRITE_ONLY`로 강제됩니다.

## 9) Spell 후보 검증 규칙 심화
`spell.py`의 `accept_spell_candidate()`는 아래를 검증합니다.

1. 빈 문자열/비출력 문자
2. 최대 길이 초과
3. 원문 대비 길이 비율 범위
4. 숫자 토큰 보존 여부
5. 권차 숫자 보존 여부
6. 편집 거리 비율

특히 `numeric_mismatch`, `volume_mismatch`는 도서 검색에서 오정정을 막는 핵심 방어선입니다.

## 10) Spell candidate 모드
`QS_SPELL_CANDIDATE_MODE`에 따라 provider 입력이 달라집니다.

1. `hint`: 후보를 참고 정보로만 사용
2. `prefill`/`best`: 최고 점수 후보를 provider 입력으로 사용

또한 candidate generator는 아래 설정을 사용합니다.
- `QS_SPELL_CANDIDATE_ENABLE`
- `QS_SPELL_CANDIDATE_MAX`
- `QS_SPELL_CANDIDATE_TOPK`
- `QS_SPELL_EDIT_DISTANCE_MAX`

## 11) Rewrite JSON 계약
`rewrite.py`는 LLM 응답에서 JSON object를 추출한 뒤 `q_rewrite`를 검증합니다.

실패 유형:
1. `invalid_json`
2. `too_long`
3. `no_change`
4. `forbidden_char`

LLM이 문장을 잘 만들어도 계약을 만족하지 못하면 채택하지 않습니다.

## 12) reason code 병합 로직
`_merge_reason_codes()`는 gate 결과와 spell/rewrite/rag 메타를 합칩니다.

예시:
- `SPELL_ERROR_TIMEOUT`
- `SPELL_REJECT_EDIT_DISTANCE`
- `REWRITE_ERROR_PROVIDER_ERROR`
- `REWRITE_REJECT_INVALID_JSON`
- `RAG_NO_CANDIDATES`

이 코드를 Search Service에서 수집하면 실패 유형 통계를 만들기 쉽습니다.

## 13) enhance 캐시 운용 팁
1. allow 캐시와 deny 캐시를 분리합니다.
2. deny TTL을 짧게(`120s`) 가져가 재시도를 허용합니다.
3. 알고리즘 변경 시 version 키를 올려 캐시 오염을 차단합니다.

## 14) 실패 재현 시나리오
아래 케이스를 직접 만들면 정책 검증이 수월합니다.

1. 낮은 budget으로 `LOW_BUDGET` 유도
2. 같은 canonical key 반복 호출로 `COOLDOWN_HIT` 확인
3. per-query cap 초과로 `PER_QUERY_CAP` 확인
4. rewrite provider 다운으로 `REWRITE_ERROR_*` 확인
