# I-0350 — LLM 비용/쿼터/속도 가드레일 (alert + auto-throttle)

## Goal
챗봇 운영 중 비용 급증과 트래픽 급증에 자동 대응하는 보호 장치를 구축한다.

## Why
- 챗은 비용 민감 기능이며 피크 구간에서 폭증 위험이 큼

## Scope
### 1) 예산 정책
- tenant/user/day budget
- 목적별(qurey rewrite, answer) 예산 분리

### 2) 자동 스로틀
- 임계치 초과 시 동적 rate limit
- 우선순위 낮은 요청 degrade

### 3) 알림
- budget burn rate 알람
- 임계치 도달/초과 이벤트

### 4) 관측
- token/cost p95, per-user spend, blocked request count

## DoD
- 비용 급증 상황에서 자동 스로틀 동작
- 운영자가 예산 소진 전 사전 인지 가능

## Codex Prompt
Add LLM cost guardrails:
- Implement budget quotas and dynamic throttling policies.
- Emit alerts for burn-rate anomalies and threshold breaches.
- Track per-tenant/user token and cost metrics.
