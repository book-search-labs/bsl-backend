# B-0227 — AuthN/AuthZ (User/Admin) + Rate Limit + Admin RBAC

## Goal
For operating API standards, BFF will introduce **Certification/Activity/Late Limit**.
- User/Admin
- RBAC(admin role/role permission)
- API rate limit + abuse prevention

## Background
- Ops UI, Reindex, Policy Change, Model Rollout, etc. “Expand Work”
If there is no authority and audit (audit), you cannot operate.
- Vulnerability → rate-limit required for scanning/autocompleteness scramble/bot.

## Scope (Sprint 1: minimal but real)
### 1) Authentication
- User:
  - (Optional) JWT (access token)
  - (optional) Session cookie (web center)
- Admin:
  - Issuer/audience or separate realm
  - without admin token   TBD  accessible

### 2) Authorization (RBAC)
- DB tables (assumed):
  - New  TBD  ,   TBD  ,   TBD   (or similar)
- Permission model:
  - `OPS_REINDEX_RUN`, `OPS_REINDEX_CANCEL`
  - `POLICY_EDIT`, `EXPERIMENT_ROLLOUT`, `MODEL_ROLLOUT`
  - `PRODUCT_EDIT`, `PAYMENT_REFUND`, ...
- BFF middleware/annotation

### 3) Rate limiting
- Strategy:
  - key = (ip + user_id or anon) + route
  - bucket per endpoint group
- Basic Policy (e.g.):
  - `/search`: 60 req/min/user
  - `/autocomplete`: 300 req/min/user
  - `/admin/*`: 30 req/min/admin
- store:
  - Redis token bucket
  - (local) in-memory (dev only)

### 4) Audit logging (Admin actions)
- Risk Endpoint:
  - reindex trigger, synonym deploy, model rollout, policy edit
- before/after + request id/trace id

### 5) Error contract
- 401/403/429 Error format included in B-0226 contract

## Non-goals
- WAF / Bot Detection Advanced (Phase 10)
- 2FA/Change workflow (option, follow)

## DoD
- User/Admin
- Admin RBAC is enforced in endpoint units
- Rate -limit is applied based on Redis and returns 429
- Admin hazardous job audit log left
- Local/dev provides easy bypass options (environmental variables)

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
