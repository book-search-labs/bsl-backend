---
title: "24. Rerank 2-Stage 오케스트레이션: Heuristic + MIS"
slug: "bsl-backend-series-24-rerank-two-stage-orchestration"
series: "BSL Backend Technical Series"
episode: 24
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 24. Rerank 2-Stage 오케스트레이션: Heuristic + MIS

## 핵심 목표
Ranking Service가 "모델 1회 호출"이 아니라 2-stage 파이프라인으로 리스크를 분산하는 구조를 코드 기준으로 설명합니다.

핵심 구현 파일:
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankService.java`
- `services/ranking-service/src/main/java/com/bsl/ranking/mis/MisClient.java`

## 1) 진입 흐름
`rerank()`는 아래 순서로 실행됩니다.

1. 후보 수집/정리
2. guardrail 적용(size, timeout, candidate 수)
3. feature enrichment
4. StagePlan 계산
5. stage1 -> stage2 실행
6. 최종 정렬/응답 생성

## 2) StagePlan 계산
`resolveStagePlan()`은 옵션을 읽어 두 stage를 구성합니다.

- `stage1.enabled` 기본 false
- `stage2.enabled` 기본 true
- topK는 요청값 + guardrail로 제한
- model override 반영

## 3) timeout 분할
`splitTimeout()` 규칙:

- stage1+stage2 둘 다 활성: `stage1=40%`, `stage2=60%`
- 하나만 활성: 전체 timeout을 해당 stage에 할당

`STAGE1_TIMEOUT_RATIO=0.4`가 코드 상수로 고정되어 있습니다.

## 4) stage1 동작
`executeStage1()`은 다음을 수행합니다.

1. skip 조건 검사
2. MIS 사용 가능하면 MIS scoring
3. 불가/실패 시 heuristic scoring
4. 정렬 후 topK 추출

결과는 stage2 입력 후보군으로 전달됩니다.

## 5) stage2 동작
`executeStage2()`는 최종 rerank 단계입니다.

- MIS eligible이면 MIS 호출
- timeout/error면 stage1 결과로 degrade
- reason code:
  - `timeout_degrade_to_stage1`
  - `error_degrade_to_stage1`

즉, stage2 실패가 전체 실패로 번지지 않습니다.

## 6) MIS 호출 조건
`misEligible()` 조건:

1. MIS enabled
2. timeout > 0
3. 후보 수 >= `minCandidatesForMis`
4. query 길이 >= `minQueryLengthForMis`

조건 미충족이면 MIS를 건너뛰고 heuristic을 사용합니다.

## 7) scoreWithMis 내부 구성
`scoreWithMis()`는 MIS 호출 전에 doc별 score cache를 먼저 조회합니다.

- cache hit: 점수 재사용
- cache miss만 묶어 MIS 배치 호출
- MIS 응답 길이 불일치면 즉시 예외 처리

이 구조로 MIS 비용과 지연을 줄입니다.

## 8) 최종 정렬 규칙
`sortScored()` 정렬 기준:

1. score desc
2. lexRank asc
3. vecRank asc
4. docId asc

동점에서도 결과가 안정적으로 재현됩니다.

## 9) reason code 구조
stage 결과는 response debug에 stage별 reason code로 남습니다.

예시:
- `stage1:skip_disabled`
- `stage2:skip_not_eligible`
- `stage2:timeout_degrade_to_stage1`

문제 분석 시 어떤 단계에서 degrade됐는지 즉시 확인 가능합니다.

## 10) MIS 요청 payload 구성
`MisClient.score()`는 각 candidate를 `pair`로 변환합니다.

포함 필드:
- `pair_id`, `query`, `doc_id`, `doc`
- feature subset(`lexRank`, `vecRank`, `rrfScore`, `issuedYear`, `volume`, `editionLabels`)

헤더로 `x-trace-id`, `x-request-id`, `traceparent`를 전달합니다.

## 11) 로컬 검증
```bash
curl -sS http://localhost:8082/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":{"text":"해리포터"},"candidates":[...],"options":{"debug":true,"timeoutMs":300}}' | jq
```

확인 포인트:
1. `debug.stageDetails.stage1/2`
2. `debug.reasonCodes`
3. `model`이 heuristic인지 MIS인지

## 12) 구현 의도
2-stage는 정확도만을 위한 구조가 아니라, 실패 복원력을 위한 구조입니다.

모델 호출이 흔들려도 stage1 결과가 남아 있으므로 "응답 불능"이 아니라 "품질 저하"로 수렴시킬 수 있습니다.
