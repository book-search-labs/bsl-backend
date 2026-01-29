# I-0311 — OWASP 기본 + 헤더/CORS/CSRF 전략 (Security Baseline)

## Goal
서비스 런칭에 필요한 **보안 기본선(OWASP Top 10 대응 관점)**을 갖추고,
BFF 중심으로 **보안 헤더/CORS/CSRF 정책**을 확정한다.

## Why
- “토큰/세션/권한”이 들어가면 보안 사고 가능성이 급증
- Admin 기능(ops/reindex/merge)은 특히 위험 → 기본 가드레일 필수

## Scope
### 1) 인증/인가 정책 정리(연계: B-0227)
- User/Admin 토큰 분리
- Admin RBAC + 감사 로그(audit_log) 연계
- 민감 작업에 대해 추가 보호(선택: 2인 승인)

### 2) HTTP Security Headers (BFF)
- HSTS(HTTPS 시)
- X-Content-Type-Options, X-Frame-Options(or CSP frame-ancestors)
- CSP(최소)
- Referrer-Policy
- Permissions-Policy

### 3) CORS 정책
- 허용 origin 화이트리스트(환경별)
- credentials 사용 여부 명확화
- preflight 캐시(필요 시)

### 4) CSRF 전략
- 쿠키 기반 세션이면 CSRF 토큰 필수
- Bearer 토큰 기반이면 CSRF 위험 낮지만,
  - Admin UI에서 쿠키/세션 쓰면 별도 고려
- 최종 결론/선택을 문서로 고정

### 5) Input validation / rate limiting / abuse
- request size 제한
- JSON schema validation(계약 기반)
- endpoint별 rate limit (B-0227과 연결)
- 업로드(문서/파일) 제한(확장 시)

### 6) 보안 체크리스트 문서
- `docs/SECURITY_BASELINE.md`
- 점검 항목 + 운영 시 주의사항

## Non-goals
- 완전한 WAF/IDS/보안관제(초기 범위 밖)
- 침투테스트/감사(추후)

## DoD
- BFF에서 보안 헤더/CORS/CSRF 정책 적용
- 입력 검증 + request size 제한 + 기본 rate limit 적용(또는 연계)
- 보안 체크리스트 문서 + “선택한 전략” 명확화
- Admin 위험 엔드포인트에 추가 방어(최소: 권한+감사로그)

## Codex Prompt
Add security baseline:
- Implement standard HTTP security headers and environment-based CORS policy in BFF.
- Decide and implement CSRF strategy consistent with auth mechanism.
- Add request size limits, validation, and basic abuse protections.
- Produce SECURITY_BASELINE.md with an OWASP-aligned checklist.
