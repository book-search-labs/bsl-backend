---
title: "09. MIS: 모델 호출을 서비스로 분리하기"
slug: "bsl-backend-series-09-mis-inference-layer"
series: "BSL Backend Technical Series"
episode: 9
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 09. MIS: 모델 호출을 서비스로 분리하기

## 문제
모델 호출 로직이 Search/Ranking/Query에 흩어져 있으면, 모델 교체/실패 복구/실험 제어가 어려워집니다.

## 1) MIS API 표면
`services/model-inference-service/app/api/routes.py`

- `POST /v1/score`
- `POST /v1/embed`
- `POST /v1/spell`
- `GET /v1/models`
- `GET /ready`
- `GET /health`

legacy 호환용 `/embed`도 남겨 두었습니다.

## 2) 요청 제한기 (`core/limits.py`)
`RequestLimiter`가 semaphore + queue를 함께 사용합니다.

- queue 초과: `429 overloaded`
- 대기 timeout: `504 queue_timeout`

핵심 env:
- `MIS_MAX_CONCURRENCY`
- `MIS_MAX_QUEUE`
- `MIS_TIMEOUT_MS`

## 3) 동적 배치 (`core/batcher.py`)
배치 키는 `(task, model_id)`입니다.

- `MIS_BATCH_ENABLED`
- `MIS_BATCH_WINDOW_MS`
- `MIS_BATCH_MAX_PAIRS`

짧은 윈도우에서 쿼리를 모아 GPU/CPU 호출 효율을 높입니다.

## 4) 모델 레지스트리와 canary
`core/registry.py`가 모델 선택을 담당합니다.

- `MIS_MODEL_REGISTRY_PATH`
- `MIS_REGISTRY_REFRESH_MS`
- model spec의 `canary`, `canary_weight`

canary weight가 켜진 모델은 확률적으로 선택됩니다.

## 5) 백엔드 유형
`ModelManager`는 spec에 따라 백엔드를 분기합니다.

- `onnx`
- `onnx_cross`
- `baseline_ltr`
- `toy`

임베딩/철자도 별도 manager(`EmbedManager`, `SpellManager`)로 분리했습니다.

## 6) spell fallback
spell 모델 로딩 실패 시 fallback 정책이 있습니다.

- `MIS_SPELL_FALLBACK=toy`

로컬 실험에서 모델 파일이 없을 때도 API 경로를 유지하는 데 유용했습니다.

## 로컬 점검
```bash
curl -sS http://localhost:8005/v1/models | jq
curl -sS http://localhost:8005/v1/embed -H 'Content-Type: application/json' -d '{"texts":["테스트"],"normalize":true}' | jq
```

## 7) 설정 기본값 심화
`settings.py` 기준 주요 기본값:

1. concurrency/queue/timeout: `4 / 32 / 200ms`
2. batching: `enabled=false`, `window=8ms`, `max_pairs=128`
3. registry refresh: `5000ms`
4. embed dim: `384`, normalize=true
5. spell timeout: `80ms`, fallback=`toy`

모델 성능 이전에 이 런타임 파라미터가 체감 latency를 좌우합니다.

## 8) 요청 제한기와 큐 동작
`limits.py`는 semaphore 획득 전에 queue 슬롯을 제어합니다.

1. queue가 가득 차면 `429 overloaded`
2. queue 대기 중 timeout이면 `504 queue_timeout`

즉, 무제한 대기를 허용하지 않고 서버 보호를 우선합니다.

## 9) Model registry 선택 전략
`registry.py`는 task/model_id 조건으로 후보를 찾고 canary를 반영합니다.

1. canary 모델 + `canary_weight>0`이면 확률적으로 선택
2. 아니면 안정 모델 선택

이 구조 덕분에 호출자 코드를 바꾸지 않고 모델 전환 실험이 가능합니다.

## 10) backend별 특징
1. `onnx`: 일반 추론
2. `onnx_cross`: query-doc pair 점수화
3. `baseline_ltr`: 규칙/기초 모델
4. `toy`: 로컬 개발용 mock

특히 `onnx_cross`는 doc 텍스트가 비면 예외가 발생할 수 있어 입력 검증이 중요합니다.

## 11) 로컬 검증 팁
1. 배치 비활성 상태로 먼저 안정성 확인
2. 이후 `MIS_BATCH_ENABLED=true`로 처리량 비교
3. registry 파일 변경 후 refresh 주기 내 반영 확인
4. `/v1/models` 응답으로 canary 노출 여부 확인

## 12) 실패 재현 시나리오
1. `MIS_MAX_QUEUE`를 작게 두고 burst 요청으로 `overloaded` 확인
2. timeout을 짧게 두고 `queue_timeout` 확인
3. 잘못된 model_id 요청으로 fallback 동작 확인
