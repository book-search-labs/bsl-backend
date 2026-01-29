# I-0313 — CI/CD (Build/Test/Distribution) + Separate Environment

## Goal
Multi-Service (BFF/QS/SR/AC/RS/MIS + Web User/Admin)
New * Build a consistent CI pipeline** and separate dev/stage/prod environment.

## Why
- We will continue to change to the ticket unit. If the distribution is manual, it is impossible to operate.
- To attach Contract/E2E/Offline eval gate, CI should be based on

## Scope
### 1) CI (Pull Request)
- Backend:
  - lint/format
  - unit test
  - build (jar/wheel/image)
  - contract test
  - API E2E Smoke(Expiration: I-0310)
- Frontend(User/Admin):
  - typecheck/lint
  - build
  - Playwright smoke(optional)

### 2) Artifact build
- Docker image build + tag strategy
  - `service:gitsha`, `service:semver`
- Image Registry Push (Personal/Project Registry)

### 3) Environmental separation
- dev/stage/prod stars:
  - config(.env / values / secrets)
  - base URL(CORS), rate limit, feature flag
  - observability endpoint
- Distribution target stage first, prod after verification

### 4) CD (Optional / Pointed)
- stage:
  - push → deploy automatic
- prod:
  - manual approve or tag based release

## Non-goals
- GitOps/ArgoCD
- Multi-cylinder/multi-cylinder(add)

## DoD
- When creating a PR, CI automatically turns, merge blocks when failed
- Main merge or tag automatic until stage distribution (min.)
- Distribution Log/Version Tracking (What is your commit in)

## Codex Prompt
Set up CI/CD:
- Add GitHub Actions pipelines for each service and for web-user/web-admin.
- Include lint, tests, build, docker image build/push, and run contract + E2E smoke checks.
- Support dev/stage/prod config separation and a simple promotion flow.
