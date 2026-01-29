# I-0320 — Model artifact storage/distribution (local→object storage)

## Goal
Models used in MIS (ONNX/Toc Knight/Metrodata)
New *Version Management + Safety Distribution + Rollbackable** Make it.

## Why
- Difficult to rollback/experience/sailing if hardcoded model files into container
- model registry(version) and artifact(file) should be separated

## Scope
### 1) Artifact Storage
- Initial: S3 compatible (minio possible) or simple object storage
- Tag:
  - `models/{model_type}/{name}/{version}/`
  - `model.onnx`, `tokenizer.json`, `config.json`, `metadata.json`, `checksum.sha256`

### 2) Distribution Method
- MIS startup:
  - Download Active Model (Cache Directory)
  - checksum validation after load
- hot reload(optional):
  - Model Change Event Detection → New Version Load → Traffic Switch

### 3) Operating function
- API( TBD  )
- Fallback when download failed/delete failed:
  - Home
  - rerank off/degrade

## Non-goals
- Complete model hub/recommended/quarter(add)

## DoD
- artifact Upload/Download Automation(Script/CI)
- MIS loads model based on active version of model registry
- Model rollback is possible with “without file change” version switch

## Codex Prompt
Implement model artifact storage & deployment:
- Define artifact layout and upload scripts.
- Add MIS logic to fetch, verify checksum, cache, and load active model version.
- Expose /v1/models and ensure safe fallback to previous model on failure.
