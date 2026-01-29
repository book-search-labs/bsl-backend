# I-0304 — Log Collection/Sampling/Communication Policy (structured logging + correlation)

## Goal
All service logs**Prostruct(JSON)** and guarantee the correlation** with **trace id/request id
Copyright (C) 2013 Sumitomo Mitsui Card Co., Ltd. All Rights Reserved.

## Why
- “Log” in Disability/Quality Issues Last Proof
- If you have any questions, please feel free to contact us.
- To prevent cost bombs, you need a sampling/billing policy

## Scope
### 1) Log schema standard (v1)
All Service Common Field:
- `timestamp`, `level`, `service`, `env`, `version`
- `request_id`, `trace_id`, `span_id`
- `route`, `method`, `status`, `latency_ms`
-  TBD     TBD    TBD 
- New  TBD  ,   TBD  ,   TBD  
-  TBD  (outbox/kafka related),   TBD  (when possible)

Payment Terms:
- access token, api key, password, raw PII

### 2) Collection pipeline (local/staying)
1 (Light): Loki + Promtail + Grafana Explore
OpenSearch Dashboards + FluentBit

> v1 recommends Loki

### 3) Sampling/Level Policy
- prod: INFO Basic, DEBUG Prohibition (specific request id only allow)
- error/timeout always collect 100%
- Success logs are sampling/reagents (optional)

### 4) Retention
- dev: 3~7 days
- Stage: 7~14 days
- prod: 14~30days

### 5) Document/operation guide
- New  TBD  : schema/masking/sampling/Search query example

## Non-goals
- SIEM/Security Control Level Rule (Extra)
- Copyright (c) 2014. All Rights Reserved.

## DoD
- All services include output + request id/trace id
- Logs can be retrieved from the local/stay area (Dashboard/Explore)
- Masking Rules Apply (Cycle/PII Exposure 0)
- Management Policy Documentation + Reflections

## Codex Prompt
Implement structured logging & collection:
- Standardize JSON log schema across services with request/trace correlation.
- Set up Loki/Promtail (or ELK) for local/stage, including retention.
- Add masking for secrets/PII and guidelines for log levels/sampling.
- Provide docs and example queries for incident debugging.
