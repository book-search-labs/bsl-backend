---
title: "14. BFF 보안 체인: Auth, RBAC, RateLimit, Abuse"
slug: "bsl-backend-series-14-bff-security-filter-chain"
series: "BSL Backend Technical Series"
episode: 14
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 14. BFF 보안 체인: Auth, RBAC, RateLimit, Abuse

## 핵심 목표
보안 로직을 거대 클래스 하나에 넣지 않고, 필터 체인으로 분할해 실패 지점을 정확히 식별합니다.

핵심 구현:
- `SecurityHeadersFilter`
- `CsrfProtectionFilter`
- `AuthFilter`
- `RateLimitFilter`
- `AbuseDetectionFilter`
- `AdminRbacFilter`
- `AdminRiskApprovalFilter`
- `AdminAuditFilter`

## 1) 필터 순서(중요)
`Ordered.HIGHEST_PRECEDENCE` 기준 주요 순서:

- `+5`: `SecurityHeadersFilter`
- `+10`: `CsrfProtectionFilter`
- `+10`: `AuthFilter`
- `+20`: `RateLimitFilter`
- `+25`: `AbuseDetectionFilter`
- `+30`: `AdminRbacFilter`
- `+35`: `AdminRiskApprovalFilter`
- `+40`: `AdminAuditFilter`

이 순서가 고정돼야 응답 코드 해석이 안정적입니다.

## 2) 인증 세션 추출
`AuthFilter`는 세션 ID를 두 경로에서 받습니다.

1. `x-session-id` 헤더
2. `Authorization: Bearer session:*`

유효하지 않으면 이후 필터로 넘기지 않고 조기 차단합니다.

## 3) Rate Limit + Abuse Detection
- `RateLimitFilter`: 키 단위 요청량 제한
- `AbuseDetectionFilter`: 실패/위험 패턴 누적 후 일정 시간 차단

즉, 순간 폭주와 반복 악성 패턴을 분리해서 방어합니다.

## 4) Admin 전용 보호막
관리자 경로에는 추가 보안 단계가 붙습니다.

1. `AdminRbacFilter`: 권한 매트릭스 체크
2. `AdminRiskApprovalFilter`: 고위험 경로는 `x-approval-id` 필수

승인 ID 포맷이 틀리면 `invalid_approval_id`로 차단합니다.

## 5) 감사 로그와 PII 마스킹
`AdminAuditFilter`는 요청/응답을 감사 로그에 남기되 `PiiMasker`를 통해 민감정보를 마스킹합니다.

관련 설정:
- `BFF_*`, `SECURITY_*`
- `PiiMaskingProperties`

“감사는 남기되 개인정보는 최소화”를 코드 레벨에서 강제합니다.

## 로컬 점검
```bash
# 세션/권한/승인 헤더를 바꿔가며 같은 admin API를 호출해
# 어느 필터에서 차단되는지 상태코드와 에러코드로 확인
```

## 6) 필터별 책임 분리 요약
1. `SecurityHeadersFilter`: 보안 헤더 주입
2. `CsrfProtectionFilter`: 상태 변경 요청 보호
3. `AuthFilter`: 세션/토큰 기반 인증
4. `RateLimitFilter`: 요청량 제한
5. `AbuseDetectionFilter`: 에러 패턴 기반 차단
6. `AdminRbacFilter`: 관리자 권한 검증
7. `AdminRiskApprovalFilter`: 고위험 요청 승인 검증
8. `AdminAuditFilter`: 감사 로그 기록

단일 필터가 모든 보안을 처리하지 않도록 분리한 구조입니다.

## 7) RateLimit identity 해석
`RateLimitFilter`는 identity를 아래 순서로 해석합니다.

1. admin 인증이면 `admin:{id}`
2. user 인증이면 `user:{id}`
3. 없으면 `x-forwarded-for`
4. 마지막 fallback은 `remoteAddr`

같은 엔드포인트라도 사용자 유형별로 제한 키가 달라집니다.

## 8) AbuseDetection 동작
`AbuseDetectionFilter`는 응답 status를 보고 오류를 누적합니다.

1. 설정된 error status 집합과 매칭
2. window 내 threshold 초과 시 block
3. block 상태면 즉시 429(`abuse_blocked`)

일시 오류 폭주를 자동으로 흡수하는 역할입니다.

## 9) Admin 승인 필터 핵심 검증
`AdminRiskApprovalFilter`는 아래를 검증합니다.

1. `x-approval-id` 존재 및 숫자 형식
2. approval row 존재
3. status=APPROVED
4. expires_at 만료 여부
5. 승인 action과 현재 요청 일치 여부
6. 요청 admin과 승인 요청자 일치 여부(가능한 경우)

모두 통과해야 risky 경로를 실행합니다.

## 10) 로컬 검증 시나리오
1. 승인 헤더 없이 risky admin API 호출
2. 만료된 approval id로 호출
3. 다른 action으로 발급된 approval id 재사용
4. 정상 승인 id로 통과 확인

이 네 케이스를 자동화해 두면 보안 회귀를 빠르게 잡을 수 있습니다.
