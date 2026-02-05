# I-0304 — 로그 수집/샘플링/보관 정책 (structured logging + correlation)

## Goal
모든 서비스 로그를 **구조화(JSON)** 하고, **trace_id/request_id로 상관관계**를 보장하며,
운영 가능한 **수집/검색/보관(retention) 정책**을 확정한다.

## Why
- 장애/품질 이슈에서 “로그”는 마지막 증거
- 트레이스/메트릭만으로는 **원인 파악이 불충분**한 경우가 많음
- 비용 폭탄을 막으려면 샘플링/보관 정책이 필요

## Scope
### 1) Log schema 표준(v1)
모든 서비스 공통 필드:
- `timestamp`, `level`, `service`, `env`, `version`
- `request_id`, `trace_id`, `span_id`
- `route`, `method`, `status`, `latency_ms`
- `user_id`(가능하면 해시/익명), `session_id`(해시)
- `error.type`, `error.message`, `error.stack`(선택)
- `event_type`(outbox/kafka 관련), `dedup_key`(가능하면)

금지/마스킹:
- access token, api key, password, raw PII(이메일/전화 등) → 마스킹 규칙

### 2) 수집 파이프라인(로컬/스테이징)
선택지 1 (가벼움): Loki + Promtail + Grafana Explore  
선택지 2 (정석): ELK/OpenSearch Dashboards + FluentBit

> v1은 Loki를 추천(구성이 단순)

### 3) 샘플링/레벨 정책
- prod: INFO 기본, DEBUG 금지(특정 request_id만 allow)
- error/timeout은 항상 100% 수집
- 성공 로그는 샘플링/요약(선택)

### 4) Retention
- dev: 3~7일
- stage: 7~14일
- prod: 14~30일(프로젝트 규모 기준)

### 5) 문서/운영 가이드
- `docs/LOGGING.md`: 스키마/마스킹/샘플링/검색 쿼리 예시

## Non-goals
- SIEM/보안 관제 수준의 룰(추후)
- 완전한 개인정보 파기(삭제 티켓과 연계)

## DoD
- 모든 서비스가 JSON 로그로 출력 + request_id/trace_id 포함
- 로컬/스테이지에서 로그 검색 가능(대시보드/Explore)
- 마스킹 규칙 적용(시크릿/PII 노출 0)
- retention 정책 문서화 + 설정 반영

## Codex Prompt
Implement structured logging & collection:
- Standardize JSON log schema across services with request/trace correlation.
- Set up Loki/Promtail (or ELK) for local/stage, including retention.
- Add masking for secrets/PII and guidelines for log levels/sampling.
- Provide docs and example queries for incident debugging.
