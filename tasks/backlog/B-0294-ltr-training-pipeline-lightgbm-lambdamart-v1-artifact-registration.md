# B-0294 — LTR Learning Pipeline (LightGBM LambdaMART v1) + Model Artifact Registration

## Goal
Create the first static LTR model.

- Input:   TBD   + point-in-time feature snapshots
- Learning: LightGBM LambdaMART
- Output:
  - model artifact (`.txt` or `.bin`, + feature list)
  - Save eval results (gate from the following ticket B-0295)
  - Registered model registry (canary/ops after activation)

## Background
- Cross-encoder is used only for expensive topR
- LTR **cheap 1st sort** is easy to operate/manualize, most widely used in the practice

## Scope
### 1) Training data assembly
- Configuration of query group units:
  - group key: `query_hash` (+ date bucket)
- label + features:
  - doc/query-doc features + match features (BM25 score, etc.)
- train/valid split:
  - time-based split recommendations (valid last N)
- class imbalance treatment:
  - Sample weights(optional)

### 2) Model training (LightGBM ranker)
- objective: `lambdarank`
- metrics:   TBD  ,   TBD   (Required)
- hyperparams v1:
  - num leaves, learning rate, min data in leaf, feature fraction, etc.

### 3) Artifact & registry
- artifact generation:
  - model file + `features.yaml` hash + training config + dataset snapshot info
-  TBD  :
  - type: `LTR`
  - name: `ltr_lambdamart_v1`
  - version: semver or timestamp
  - artifact uri: local path → (I-0320 object store extension)

### 4) Reproducibility
- Seed fixing
- training run metadata
  - git sha, dataset range, feature snapshot date range

## Non-goals
- Optimal Hyperparrameter Navigation (Optuna, etc.)
- deep model LTR

## DoD
- Learning pipelines in local/staking run end-to-end
- Create a prototype + registry registration
- ndcg@10 report output from valid
- Learning Reproduction (A similar result when entering a day)

## Codex Prompt
Build LTR training pipeline:
- Assemble training data by time-joining ltr_training_example with daily feature snapshots (point-in-time).
- Train a LightGBM LambdaMART ranker with reproducible config/seed and produce artifacts with metadata.
- Register the model into model_registry including artifact_uri and features.yaml hash, and output a training report with ndcg@10.
