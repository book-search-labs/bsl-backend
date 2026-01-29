# I-0343 — Rate-limit/abuse 패턴 탐지(봇/스크래핑) + 차단 정책

## Goal
봇/스크래핑/과도한 호출로 인한 비용/성능 악화를 탐지하고 차단한다.
- “검색/자동완성/챗”은 abuse에 매우 취약

## Why
- 검색 API는 데이터 수집 타겟이 되기 쉽고
- 챗(LLM)은 비용 폭탄이 될 수 있음

## Scope
### 1) 탐지 신호 수집
- IP / user_id / api_key / user-agent / path
- req/sec, error rate, identical query 반복, unusual pagination
- headless UA/빈 UA/짧은 세션에서 과도한 호출

### 2) 차단 정책
- 단계형:
  1) soft limit(429 + Retry-After)
  2) challenge(간단 토큰/서명)
  3) hard block(기간 차단)
- endpoint별 정책:
  - /autocomplete: 짧은 윈도우 강한 제한
  - /search: 중간
  - /chat: 가장 강함(사용자별 예산)

### 3) 운영 도구/로그
- 차단 이벤트 로그(audit_log/abuse_log)
- Admin에서 top offenders 조회(연계 티켓 가능)

## Non-goals
- CAPTCHA/고급 WAF 통합(추후)

## DoD
- 최소 3가지 abuse 패턴을 탐지/차단 가능
- rate-limit 정책이 문서화되고 운영자가 조정 가능
- 차단/해제 로그가 남고, 오탐/정상 트래픽 영향이 제한적

## Codex Prompt
Implement abuse detection & blocking:
- Collect request features and compute basic abuse heuristics.
- Enforce tiered rate-limit/block policies per endpoint.
- Record abuse actions in logs/audit and add minimal admin visibility.
