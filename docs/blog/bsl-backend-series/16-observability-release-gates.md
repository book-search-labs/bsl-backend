---
title: "16. 로컬 품질 회귀 게이트: Contract, Eval, Chat Matrix"
slug: "bsl-backend-series-16-local-quality-regression-gates"
series: "BSL Backend Technical Series"
episode: 16
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 16. 로컬 품질 회귀 게이트: Contract, Eval, Chat Matrix

## 핵심 목표
로컬 환경만으로도 코드 변경 직후 계약 파손/품질 회귀를 잡아내는 테스트 체계를 만듭니다.

진입점:
- `scripts/test.sh`

## 1) `scripts/test.sh` 구조
현재 스크립트는 `34` 단계 메시지로 구성돼 있고, 대부분은 `RUN_*` 환경변수로 켜는 선택 게이트입니다.

기본 실행에서 바로 의미 있는 항목:
1. 계약 스키마 검증 (`validate_contracts.py`)
2. 계약 호환성 게이트 (`contract_compat_check.py`)
3. 피처 스펙 검증 (`validate_feature_spec.py`)

## 2) 검색/랭킹 품질 게이트
옵션으로 아래를 활성화합니다.

- `RUN_EVAL=1`: offline eval gate
- `RUN_RERANK_EVAL=1`: rerank eval gate

rerank gate는 Ranking/MIS/OpenSearch 의존성을 사전 점검한 뒤 실행합니다.

## 3) 챗 회귀 게이트
챗 경로는 세분화된 스크립트로 평가합니다.

대표 항목:
- `RUN_CHAT_CONTRACT_COMPAT_EVAL=1`
- `RUN_CHAT_REASON_TAXONOMY_EVAL=1`
- `RUN_CHAT_ALL_EVALS=1`

관련 스크립트:
- `chat_contract_compat_eval.py`
- `chat_reason_taxonomy_eval.py`
- `chat_graph_parity_eval.py`
- `chat_eval_matrix.py`

즉, 계약 적합성/reason taxonomy/parity를 분리해서 실패 원인을 좁힙니다.

## 4) 선택 게이트가 많은 이유
모든 게이트를 항상 돌리면 로컬 반복 속도가 떨어집니다. 그래서 빠른 루프와 깊은 검증을 분리했습니다.

추천 실행 프로필:

1. 빠른 확인
```bash
./scripts/test.sh
```

2. 검색/랭킹 포함
```bash
RUN_EVAL=1 RUN_RERANK_EVAL=1 ./scripts/test.sh
```

3. 챗 회귀 포함
```bash
RUN_CHAT_CONTRACT_COMPAT_EVAL=1 \
RUN_CHAT_REASON_TAXONOMY_EVAL=1 \
RUN_CHAT_ALL_EVALS=1 \
./scripts/test.sh
```

## 5) 이 편의 결론
로컬 사이드프로젝트에서도 품질 게이트를 코드화하면, “나중에 확인”이 아니라 “커밋 전에 차단”이 가능해집니다.

## 6) `scripts/test.sh` 단계 그룹화
현재 34단계를 기능군으로 나누면 아래와 같습니다.

1. 계약/스키마 검증
2. 검색/랭킹 eval 게이트
3. 챗 계약/분류/parity 게이트
4. 챗 고급 시나리오 게이트(세션/데이터/예산/정책/캐시/adversarial 등)
5. canonical/e2e 선택 게이트

기본 실행은 빠르게, 선택 실행은 깊게 검증하는 구조입니다.

## 7) 자주 쓰는 실행 조합
1. 계약 중심 빠른 루프
```bash
./scripts/test.sh
```

2. 검색 품질 검증 포함
```bash
RUN_EVAL=1 RUN_RERANK_EVAL=1 ./scripts/test.sh
```

3. 챗 핵심 회귀 포함
```bash
RUN_CHAT_CONTRACT_COMPAT_EVAL=1 RUN_CHAT_REASON_TAXONOMY_EVAL=1 RUN_CHAT_ALL_EVALS=1 ./scripts/test.sh
```

4. E2E까지 포함
```bash
RUN_E2E=1 ./scripts/test.sh
```

## 8) 실패 원인 역추적 팁
1. 계약 단계 실패면 스키마/샘플부터 수정합니다.
2. rerank eval 실패면 MIS/Ranking/OpenSearch 의존성부터 확인합니다.
3. chat parity 실패면 replay/shadow diff부터 확인합니다.
4. 챗 고급 시나리오 게이트 실패는 리포트 JSON을 먼저 확인합니다.

이 순서를 지키면 불필요한 디버깅 시간을 줄일 수 있습니다.

## 9) 로컬 환경에서의 한계와 보완
1. optional 게이트가 많아 모두 항상 돌리기는 어렵습니다.
2. 따라서 변경 범위별 실행 프로필을 미리 정해두는 것이 중요합니다.
3. baseline 리포트 파일을 같이 관리하면 회귀 판정 품질이 올라갑니다.
