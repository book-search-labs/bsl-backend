# I-0313 — CI/CD (빌드/테스트/배포) + 환경 분리

## Goal
멀티 서비스(BFF/QS/SR/AC/RS/MIS + Web User/Admin)에 대해
**일관된 CI 파이프라인**을 구축하고 dev/stage/prod 환경을 분리한다.

## Why
- 티켓 단위로 계속 변경되는데 배포가 수동이면 운영이 불가능
- Contract/E2E/Offline eval gate를 붙이려면 CI가 기반이 되어야 함

## Scope
### 1) CI (Pull Request 기준)
- Backend(각 서비스):
  - lint/format
  - unit test
  - build (jar/wheel/image)
  - contract test(연계: B-0226)
  - API E2E smoke(연계: I-0310)
- Frontend(User/Admin):
  - typecheck/lint
  - build
  - (선택) Playwright smoke

### 2) Artifact build
- Docker image build + tag 전략
  - `service:gitsha`, `service:semver`
- 이미지 레지스트리 푸시(개인/프로젝트 레지스트리)

### 3) 환경 분리
- dev/stage/prod 별:
  - config(.env / values / secrets)
  - base URL(CORS), rate limit, feature flag
  - observability endpoint
- 배포 대상도 stage 먼저, 검증 후 prod(승격)

### 4) CD (선택/점진)
- stage:
  - push → deploy 자동
- prod:
  - manual approve 또는 tag 기반 release

## Non-goals
- 완전한 GitOps/ArgoCD(추후)
- 멀티클러스터/멀티리전(추후)

## DoD
- PR 생성 시 CI가 자동으로 돌고, 실패 시 merge 차단
- main merge 또는 tag 시 stage 배포까지 자동(최소)
- 배포 로그/버전 추적 가능(어느 커밋이 어떤 환경에 있는지)

## Codex Prompt
Set up CI/CD:
- Add GitHub Actions pipelines for each service and for web-user/web-admin.
- Include lint, tests, build, docker image build/push, and run contract + E2E smoke checks.
- Support dev/stage/prod config separation and a simple promotion flow.
