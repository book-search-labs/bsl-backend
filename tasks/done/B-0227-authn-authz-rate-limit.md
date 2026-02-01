# B-0227 — AuthN/AuthZ (User/Admin) + Rate Limit + Admin RBAC

## Goal
운영형 API 표준을 위해 BFF에 **인증/인가/레이트리밋**을 도입한다.
- User/Admin 인증 분리
- Admin은 **RBAC(admin_role/role_permission)** 기반
- API별 rate limit + abuse 방지

## Background
- Ops UI, Reindex, 정책 변경, 모델 롤아웃 등 “위험 작업”은
  권한과 감사(audit)가 없으면 운영 불가.
- 검색/자동완성도 스크래핑/봇에 취약 → rate-limit 필수.

## Scope (Sprint 1: minimal but real)
### 1) Authentication
- User:
  - (선택1) JWT (access token)
  - (선택2) session cookie (웹 중심)
- Admin:
  - 별도 issuer/audience or 별도 realm
  - admin 토큰 없으면 `/admin/*` 접근 불가

### 2) Authorization (RBAC)
- DB tables (assumed):
  - `admin_role`, `role_permission`, `admin_user_role` (또는 유사)
- Permission model:
  - `OPS_REINDEX_RUN`, `OPS_REINDEX_CANCEL`
  - `POLICY_EDIT`, `EXPERIMENT_ROLLOUT`, `MODEL_ROLLOUT`
  - `PRODUCT_EDIT`, `PAYMENT_REFUND`, ...
- BFF middleware/annotation으로 endpoint 권한 체크

### 3) Rate limiting
- Strategy:
  - key = (ip + user_id or anon) + route
  - bucket per endpoint group
- 기본 정책(예):
  - `/search`: 60 req/min/user
  - `/autocomplete`: 300 req/min/user
  - `/admin/*`: 30 req/min/admin
- store:
  - Redis token bucket (권장)
  - (로컬) in-memory (dev only)

### 4) Audit logging (Admin actions)
- 위험 엔드포인트:
  - reindex trigger, synonym deploy, model rollout, policy edit
- `audit_log`에 before/after + request_id/trace_id 기록

### 5) Error contract
- 401/403/429 에러 포맷을 B-0226 계약에 포함

## Non-goals
- WAF/봇 탐지 고급(Phase 10)
- 2FA/승인 워크플로(옵션, 추후)

## DoD
- User/Admin 인증이 분리되어 동작
- Admin RBAC가 endpoint 단위로 enforce됨
- Rate-limit이 Redis 기반으로 적용되고 429 반환
- Admin 위험 작업은 audit_log가 남음
- 로컬/dev에서는 간편한 bypass 옵션(환경 변수) 제공

## Observability
- metrics:
  - auth_fail_total, rbac_denied_total, ratelimit_block_total
- logs:
  - actor_id, permission, route, request_id

## Codex Prompt
Implement AuthN/AuthZ + rate limiting for BFF:
- Separate user/admin authentication.
- Enforce admin RBAC using admin_role/role_permission mapping.
- Add Redis-based token bucket rate limits per endpoint group.
- Emit audit_log entries for privileged admin actions.
- Standardize 401/403/429 error schema consistent with contracts.
