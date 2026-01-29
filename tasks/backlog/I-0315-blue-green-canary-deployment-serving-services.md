# I-0315 — Blue/Green/Canary Distribution (servation service)

## Goal
BFF/QS/SR/AC/RS/MIS
New *Unlimited distribution (Blue/Green) + Canary** Creates a standard operating strategy.

## Why
- Search/Ranking/Models are “quality/degradable” and 100% distributed at once risk
- There is an Offline eval gate, but there is a problem that only exposed to real traffic

## Scope
### 1) Deployment Strategy
- Blue/Green:
  - Two sets of same version (blue, green)
  - switch after health/ready confirmation
- Canary:
  - Increased gradient with some traffic (e.g. 1%→5%→25%→100%)
  - Automatic/Manual Rollback on Error Rate/latency/Quality Proxy

### 2) Routing standard
- BFF Standard Canary:
  - header/cookie/user bucket
  - or weight in gateway level
- MIS/RS Model Canary:
  - model registry active + canary routing policy (banner: B-0274)

### 3) Rollback procedure
- Returnable button/Cold
- Rollback City Observation Indicator Checklist Included

## Non-goals
- Fully automated virtual delivery platform (extra)

## DoD
- Blue/green transitions in stage actually work (healthcheck + switch)
- canary routing (minimum 2 steps)
- Runbook Documentation + 1 Rehearsal

## Codex Prompt
Add blue/green and canary deployment support:
- Define deployment manifests/scripts to run two versions and switch traffic safely.
- Implement canary routing strategy (weight or bucket) and rollback procedure.
- Document runbooks and verify in stage.
