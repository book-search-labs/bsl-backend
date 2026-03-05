---
title: "20. Spell Candidate Generator: 사전/키보드/편집거리 후보 생성기"
slug: "bsl-backend-series-20-spell-candidate-generator"
series: "BSL Backend Technical Series"
episode: 20
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 20. Spell Candidate Generator: 사전/키보드/편집거리 후보 생성기

## 핵심 목표
`/query/enhance`의 spell 단계에서 모델 호출 전 후보군을 만들어 오정정을 줄이고, 호출 비용을 낮추는 구조를 설명합니다.

핵심 구현 파일:
- `services/query-service/app/core/spell_candidates.py`
- `services/query-service/app/core/spell.py`

## 1) 전체 구조
Spell 흐름은 두 단계입니다.

1. `SpellCandidateGenerator`가 후보 생성/점수화
2. `run_spell()`이 후보를 provider 입력으로 사용할지 결정

즉, 후보 생성기는 "모델 대체"가 아니라 "모델 보조" 레이어입니다.

## 2) 후보 생성 순서
`generate()`는 아래 소스를 순서대로 추가합니다.

1. 공백 변형 (`space`)
2. 사전 치환 (`dict_hit`)
3. 키보드 인접 변형 (`kbd_adj`)
4. 편집 변형 (`edit1`)

마지막에 점수 정렬 후 `top_k`만 반환합니다.

## 3) 설정값(핵심)
`load_config()` 기준 기본값:

- `QS_SPELL_CANDIDATE_ENABLE=false`
- `QS_SPELL_CANDIDATE_MAX=50`
- `QS_SPELL_CANDIDATE_TOPK=5`
- `QS_SPELL_EDIT_DISTANCE_MAX=2`
- `QS_SPELL_KEYBOARD_LOCALE=both`
- `QS_SPELL_CANDIDATE_MIN_SCORE=0.0`

사전 백엔드 설정:
- `QS_SPELL_DICT_BACKEND=file|redis`
- `QS_SPELL_DICT_PATH`
- `QS_SPELL_DICT_REDIS_URL`
- `QS_SPELL_DICT_REDIS_KEY`

## 4) file 사전 로더 특징
file 백엔드는 JSONL을 읽어 `variant -> canonical` 맵을 구성합니다.

포인트:
- `canonical`, `variants/aliases/values` 모두 인식
- 상대 경로면 서비스 루트 기준으로 보정
- 파일 `mtime` 기반 캐시(`_DICT_CACHE`)로 재파싱 비용 최소화

## 5) redis 사전 로더 특징
redis 백엔드는 `HGETALL` 결과를 그대로 variant 맵으로 사용합니다.

포인트:
- `dict_redis_url + dict_redis_key` 조합으로 메모리 캐시
- redis 장애 시 빈 사전으로 폴백

## 6) 키보드 인접 후보(한글/영문)
영문은 QWERTY 좌표 인접 키를 사용합니다.

한글은 더 복잡합니다.
- 음절 분해(`_decompose_syllable`)
- 초/중/종성별 인접 키 탐색
- 다시 음절 조합(`_compose_syllable`)

이 방식으로 오타 1스텝 후보를 생성합니다.

## 7) 편집 변형 후보
`_edit_variants()`는 토큰 단위로 아래를 수행합니다.

1. 문자 삭제
2. 인접 문자 swap
3. (거리 2 허용 시) 2차 삭제

`max_distance`와 `limit`를 넘지 않도록 제어합니다.

## 8) 점수 함수
`_score_candidate()`는 기본적으로 편집거리 비율 기반입니다.

- base: `1 - distance_ratio`
- 가산점:
  - `dict_hit` +0.2
  - `kbd_adj` +0.05
  - `edit1` +0.02

최대 1.0으로 clip합니다.

## 9) 오정정 방어선
점수 계산 전에 아래 mismatch를 차단합니다.

- `_numeric_mismatch`: 숫자 토큰 유실
- `_volume_mismatch`: 권차 번호 유실

도서 검색에서 ISBN/권차 유실은 치명적이므로 점수 0으로 즉시 제외합니다.

## 10) provider 입력 전략
`run_spell()`은 `QS_SPELL_CANDIDATE_MODE`를 확인합니다.

- `hint`: 원문을 provider에 전달하고 후보는 디버그 힌트로만 사용
- `prefill`/`best`: 최고점 후보를 provider 입력으로 사용

응답 debug에는 `candidates`, `candidate_mode`, `candidate_input`이 남습니다.

## 11) 최종 채택 검증(`accept_spell_candidate`)
모델 응답도 그대로 채택하지 않습니다.

검증 항목:
1. empty/비출력 문자
2. 길이 상한(`QS_SPELL_MAX_LEN`)
3. 길이 비율(`QS_SPELL_LEN_RATIO_MIN/MAX`)
4. 숫자/권차 보존
5. 편집거리 비율(`QS_SPELL_EDIT_DISTANCE_RATIO_MAX`)

반려 사유는 `reject_reason`으로 기록됩니다.

## 12) 실패 reason code 연결
`routes.py::_merge_reason_codes()`에서 spell 메타를 reason code로 병합합니다.

예시:
- `SPELL_ERROR_TIMEOUT`
- `SPELL_ERROR_PROVIDER_ERROR`
- `SPELL_REJECT_NUMERIC_MISMATCH`
- `SPELL_REJECT_EDIT_DISTANCE`

Search Service 쪽 품질 로그와 바로 연결하기 좋습니다.

## 13) 로컬 검증
```bash
curl -sS http://localhost:8001/query/enhance \
  -H 'Content-Type: application/json' \
  -d '{
    "q_norm":"해리 포터 01 권",
    "q_nospace":"해리포터01권",
    "reason":"ZERO_RESULTS",
    "signals":{"latency_budget_ms":400},
    "detected":{"mode":"normal"},
    "debug":true
  }' | jq
```

확인 포인트:
1. `debug.spell.candidates`
2. `debug.spell.candidate_mode`, `candidate_input`
3. `reason_codes`의 `SPELL_*`

## 14) 구현상 트레이드오프
candidate generator를 강하게 켜면 recall은 오르지만, 잘못된 후보가 상위로 올라갈 위험도 있습니다.

그래서 이 구현은 다음 원칙으로 제한합니다.
- candidate는 보조 신호로 사용
- 최종 채택은 `accept_spell_candidate`를 반드시 통과
- reject reason을 코드로 남겨 재학습 데이터로 축적
