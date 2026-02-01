# B-0294 — LTR 학습 파이프라인(LightGBM LambdaMART v1) + 모델 아티팩트 등록

## Goal
첫 번째 실전형 LTR 모델을 만든다.

- 입력: `ltr_training_example` + point-in-time feature snapshots
- 학습: LightGBM LambdaMART (ranker)
- 출력:
  - model artifact (`.txt` or `.bin`, + feature list)
  - eval 결과 저장(다음 티켓 B-0295에서 gate)
  - model_registry 등록(활성화는 이후 canary/ops)

## Background
- Cross-encoder는 비싸서 topR에만 사용
- LTR은 **cheap 1차 정렬**로 운영/설명가능성이 좋고, 실무에 가장 널리 쓰임

## Scope
### 1) Training data assembly
- query group 단위로 구성:
  - group key: `query_hash` (+ date bucket)
- label + features:
  - doc/query-doc features + match features(BM25 score 등)
- train/valid split:
  - time-based split 권장(최근 N일을 valid)
- class imbalance 처리:
  - sample weights(선택)

### 2) Model training (LightGBM ranker)
- objective: `lambdarank`
- metrics: `ndcg@10`, `map@10` (필요시)
- hyperparams v1:
  - num_leaves, learning_rate, min_data_in_leaf, feature_fraction 등

### 3) Artifact & registry
- artifact 생성:
  - model file + `features.yaml` hash + training config + dataset snapshot info
- `model_registry`에 등록:
  - type: `LTR`
  - name: `ltr_lambdamart_v1`
  - version: semver or timestamp
  - artifact_uri: local path → (I-0320에서 object store 확장)

### 4) Reproducibility
- seed 고정
- training run metadata 저장:
  - git sha, dataset range, feature snapshot date range

## Non-goals
- 최적 하이퍼파라미터 탐색(Optuna 등)
- deep model LTR

## DoD
- 로컬/스테이징에서 학습 파이프라인이 end-to-end 실행
- 모델 아티팩트 생성 + registry 등록
- valid에서 ndcg@10 리포트 산출
- 학습 재현 가능(동일 입력이면 유사 결과)

## Codex Prompt
Build LTR training pipeline:
- Assemble training data by time-joining ltr_training_example with daily feature snapshots (point-in-time).
- Train a LightGBM LambdaMART ranker with reproducible config/seed and produce artifacts with metadata.
- Register the model into model_registry including artifact_uri and features.yaml hash, and output a training report with ndcg@10.
