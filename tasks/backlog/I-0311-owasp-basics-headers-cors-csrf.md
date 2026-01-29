# I-0311 — OWASP Basic + Header/CORS/CSRF Strategy (Security Baseline)

## Goal
**Security basic line (OWASP Top 10 Point of Service)**
BFF center**Extend security header/CORS/CSRF policy**.

## Why
- When “token/session/recommended”, the possibility of security accidents
- Admin function (ops/reindex/merge) is especially dangerous → basic Guardian required

## Scope
### 1) Summary of Certification/Account Policy (Account: B-0227)
- User/Admin Token Separation
- Admin RBAC + Audit Log(audit log) Link
- Additional protection for sensitive tasks (optional: 2 person approval)

### 2) HTTP Security Headers (BFF)
- HSTS(HTTPS)
- X-Content-Type-Options, X-Frame-Options(or CSP frame-ancestors)
- CSP (min.)
- Referrer-Policy
- Permissions-Policy

### 3) CORS Policy
- Allowed origin whitelist (by environment)
- credentials use or clear
- preflight cache (required)

### 4) CSRF Strategy
- If the cookie-based session, CSRF token is required
- If Bearer token is based, CSRF is low, but
  - In the Admin UI, you can use cookies/session to consider separately
- Fixed the final conclusion/optional as a document

### 5) Input validation / rate limiting / abuse
- request size limit
- JSON schema validation
- rate limit by endpoint (connect with B-0227)
- Upload (Document/File) Limit (Exit)

### 6) Security checklist document
- `docs/SECURITY_BASELINE.md`
- Check items + maintenance notice

## Non-goals
- Complete WAF/IDS/Security Control (Out of the initial range)
- Permeability test/depression (extra)

## DoD
- Apply security header/CORS/CSRF policy in BFF
- Input verification + request size limit + base rate limit (or linkage)
- Security checklist document + "Select strategy" clarification
- Admin additional defense to risk endpoints (minimum: authority+path)

## Codex Prompt
Add security baseline:
- Implement standard HTTP security headers and environment-based CORS policy in BFF.
- Decide and implement CSRF strategy consistent with auth mechanism.
- Add request size limits, validation, and basic abuse protections.
- Produce SECURITY_BASELINE.md with an OWASP-aligned checklist.
