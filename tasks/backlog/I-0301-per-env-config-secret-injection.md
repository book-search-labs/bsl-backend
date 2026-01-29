# I-0301 — per-env config (dev/stage/prod) + secret injection/rotation (extensible)

## Goal
환경(dev/stage/prod) 별로 설정/시크릿을 분리하고,
**secret 주입/회전(rotation)** 까지 확장 가능한 구성 체계를 만든다.

## Why
- 로컬에서 돌아가던 서비스가 운영 단계로 갈 때 가장 먼저 무너지는 부분이 설정/시크릿
- BFF/MIS/LLM key/Kafka/DB/OS 등 다수 의존성을 안전하게 관리해야 함

## Scope
### 1) 설정 계층
- `config/` 디렉토리 표준화
  - `application-dev.yml`, `application-stage.yml`, `application-prod.yml` (Spring)
  - `.env.dev`, `.env.stage`, `.env.prod` (FastAPI/기타)
- 공통 규칙:
  - “코드에 값 하드코딩 금지”
  - 환경별 override는 명시적으로

### 2) Secret injection(초기 v1)
- dev: `.env` + docker compose secrets(가능하면)
- stage/prod: 아래 중 1개로 구조만 확정
  - AWS SSM Parameter Store / Secrets Manager
  - Vault
  - Kubernetes Secret

### 3) Rotation 설계
- key/versioned secret 지원
  - 예: `OPENAI_API_KEY_v1`, `OPENAI_API_KEY_v2`
- 앱은 “현재 active key”를 참조하거나 재기동 없이 reload 가능(선택)

### 4) 검증/가드
- 부팅 시 “필수 env 누락” 체크(빠르게 fail)
- secret 값 로그 출력 금지(마스킹)
- 문서: `docs/CONFIG.md` + 예시 템플릿 제공

## Non-goals
- IaC(Terraform) 완성(별도 티켓 가능)
- 완전 무중단 secret rotation 자동화(초기에는 수동 절차로 시작)

## DoD
- dev/stage/prod별 설정 파일/환경변수 체계가 repo에 정리됨
- 각 서비스가 동일 규칙으로 config를 로드하고 누락 시 fail-fast
- secret 값이 로그/에러에 노출되지 않음
- “회전 절차” 문서가 존재하고 재현 가능

## Codex Prompt
Create per-environment config & secret handling:
- Standardize config files and env var loading across services.
- Add fail-fast validation and log masking for secrets.
- Provide templates and documentation for dev/stage/prod.
- Define a rotation approach with versioned secrets and operational steps.
