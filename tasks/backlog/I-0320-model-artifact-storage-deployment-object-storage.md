# I-0320 — 모델 아티팩트 저장/배포 (로컬→오브젝트 스토리지)

## Goal
MIS에서 사용하는 모델(ONNX/토크나이저/메타데이터)을
**버전 관리 + 안전 배포 + 롤백 가능**하게 만든다.

## Why
- 모델 파일을 컨테이너에 하드코딩하면 롤백/실험/스케일이 어려움
- model_registry(버전)와 artifact(파일)를 분리해야 운영이 된다

## Scope
### 1) Artifact 저장소
- 초기: S3 호환(minio 가능) 또는 단순 object storage
- 경로 규칙:
  - `models/{model_type}/{name}/{version}/`
  - `model.onnx`, `tokenizer.json`, `config.json`, `metadata.json`, `checksum.sha256`

### 2) 배포 방식
- MIS startup:
  - active 모델 다운로드(캐시 디렉토리)
  - checksum 검증 후 load
- hot reload(선택):
  - 모델 변경 이벤트 감지 → 새 버전 로드 → 트래픽 스위치

### 3) 운영 기능
- “현재 로드된 모델 목록” API(`/v1/models`)
- 다운로드 실패/검증 실패 시 fallback:
  - 이전 버전 유지
  - rerank off/degrade(연계: B-0273)

## Non-goals
- 완전한 모델 허브/권한/쿼터(추후)

## DoD
- artifact 업로드/다운로드가 자동화(스크립트/CI)
- MIS가 model_registry의 active 버전을 기준으로 모델을 로드
- 모델 롤백이 “파일 교체 없이” 버전 스위치로 가능

## Codex Prompt
Implement model artifact storage & deployment:
- Define artifact layout and upload scripts.
- Add MIS logic to fetch, verify checksum, cache, and load active model version.
- Expose /v1/models and ensure safe fallback to previous model on failure.
